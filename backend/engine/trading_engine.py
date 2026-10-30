"""
AutoTrader Pro - Trading Engine Orchestrator
=============================================
Central orchestrator that coordinates all trading strategies, the exchange,
risk management, paper trading, smart order routing, unified position tracking,
and database persistence.

The engine's ``run_cycle()`` method is called periodically by the scheduler.
It fetches market data, runs every enabled strategy, validates signals
through the risk manager, executes trades (paper or live), and persists
everything to the database.
"""

import json
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import pandas as pd

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Trade, Signal, PortfolioSnapshot
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now, calculate_pnl, calculate_pnl_pct, format_inr

from backend.exchange.exchange_manager import ExchangeManager
from backend.risk.risk_manager import RiskManager
from backend.paper.paper_trader import PaperTrader

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.ma_pullback import MAPullbackStrategy
from backend.engine.breakout_hunter import BreakoutHunterStrategy
from backend.engine.rsi_divergence import RSIDivergenceStrategy
from backend.engine.sentiment_llm import SentimentLLMStrategy
from backend.engine.grid_trading import GridTradingStrategy
from backend.engine.price_action import PriceActionStrategy
from backend.engine.neural_net_strategy import (
    NeuralNetworkStrategy,
    WEIGHTS_PATH_BTC,
    WEIGHTS_PATH_ETH,
    WEIGHTS_PATH_ALTS,
)
from backend.engine.mean_reversion import MeanReversionStrategy
from backend.engine.scalping import ScalpingStrategy
from backend.engine.stat_arb import StatisticalArbitrageStrategy
from backend.engine.signal_aggregator import SignalAggregator
from backend.engine.order_router import SmartOrderRouter, OrderPlan
from backend.engine.position_tracker import PositionTracker, Position

try:
    from backend.engine.regime_detector import MarketRegimeDetector, regime_detector
except ImportError:
    class MarketRegimeDetector:
        def detect(self, pair: str, df: Any) -> Dict[str, Any]:
            return {"pair": pair, "regime": "NEUTRAL", "confidence": 0.5}
    regime_detector = MarketRegimeDetector()


class TradingEngine:
    """
    Main trading engine that orchestrates the full trading pipeline.

    Attributes:
        running (bool): Whether the engine is actively processing cycles.
        mode (str): 'paper' for simulated trades, 'live' for real trades.
        strategies (list[StrategyBase]): All registered strategy instances.
        exchange_manager (ExchangeManager): Market data and order execution.
        risk_manager (RiskManager): Position sizing and risk controls.
        paper_trader (PaperTrader): Paper-trade execution engine.
        order_router (SmartOrderRouter): Smart order routing and TWAP chunking.
        position_tracker (PositionTracker): Unified net position and exposure tracking.
    """

    def __init__(
        self,
        exchange_manager: Optional[ExchangeManager] = None,
        risk_manager: Optional[RiskManager] = None,
        paper_trader: Optional[PaperTrader] = None,
        mode: str = "paper",
    ):
        """
        Initialize the trading engine with all sub-systems.

        Args:
            exchange_manager: ExchangeManager instance (created if None).
            risk_manager: RiskManager instance (created if None).
            paper_trader: PaperTrader instance (created if None).
            mode: 'paper' or 'live'.
        """
        self.running: bool = False
        self.mode: str = mode

        # -- Sub-systems --
        self.exchange_manager = exchange_manager or ExchangeManager()
        self.risk_manager = risk_manager or RiskManager()
        self.paper_trader = paper_trader or PaperTrader()

        # -- Smart Order Router & Unified Position Tracker (Agent 3) --
        self.order_router = SmartOrderRouter()
        self.position_tracker = PositionTracker()
        self._init_position_tracker()

        # -- Strategies --
        self.strategies: List[StrategyBase] = [
            MAPullbackStrategy(),
            BreakoutHunterStrategy(),
            RSIDivergenceStrategy(),
            SentimentLLMStrategy(),
            GridTradingStrategy(),
            PriceActionStrategy(),
            # 1. Dedicated BTC Neural Model (10 Years Macro + DB)
            NeuralNetworkStrategy(
                name="Neural_Network_BTC",
                weights_path=WEIGHTS_PATH_BTC,
                pair_filter=["BTC/INR"],
            ),
            # 2. Dedicated ETH Neural Model (3,250+ Daily + Hourly Macro)
            NeuralNetworkStrategy(
                name="Neural_Network_ETH",
                weights_path=WEIGHTS_PATH_ETH,
                pair_filter=["ETH/INR"],
            ),
            # 3. Dedicated Major Altcoins Neural Model (SOL, XRP, BNB)
            NeuralNetworkStrategy(
                name="Neural_Network_ALTS",
                weights_path=WEIGHTS_PATH_ALTS,
                pair_filter=["SOL/INR", "XRP/INR", "BNB/INR"],
            ),
            # 4. Mean Reversion
            MeanReversionStrategy(),
            # 5. Scalping
            ScalpingStrategy(exchange_manager=self.exchange_manager),
            # 6. Statistical Arbitrage
            StatisticalArbitrageStrategy(exchange_manager=self.exchange_manager),
        ]
        # All strategies enabled by default; signal aggregator handles conflicts
        for s in self.strategies:
            s.enable()

        # -- Signal Aggregator & Regime Detection --
        self.signal_aggregator = SignalAggregator()
        self.regime_detector = regime_detector

        # -- Strategy Performance Tracking --
        self.strategy_performance: Dict[str, Dict[str, Any]] = {}
        self._init_strategy_performance()

        # -- Cycle stats --
        self._last_cycle_time: Optional[str] = None
        self._total_cycles: int = 0

        bot_logger.info(
            f"TradingEngine initialized — mode={self.mode}, "
            f"strategies={[s.name for s in self.strategies]}"
        )

    def _init_position_tracker(self) -> None:
        """Synchronize position tracker with open trades from database."""
        db = SessionLocal()
        try:
            open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
            self.position_tracker.sync_from_trades(open_trades)
            if open_trades:
                bot_logger.info(
                    f"[Engine] PositionTracker synchronized with {len(open_trades)} open trade(s)"
                )
        except Exception as exc:
            bot_logger.error(f"[Engine] Failed to initialize PositionTracker: {exc}")
        finally:
            db.close()

    def _init_strategy_performance(self) -> None:
        """Initialize per-strategy performance metrics from closed trades in the database."""
        db = SessionLocal()
        try:
            closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
            by_strategy: Dict[str, List[Trade]] = {}
            for t in closed_trades:
                strat = t.strategy or "Unknown"
                by_strategy.setdefault(strat, []).append(t)

            for s in self.strategies:
                trades = by_strategy.get(s.name, [])
                total = len(trades)
                wins = sum(1 for t in trades if (t.pnl or 0) > 0)
                losses = sum(1 for t in trades if (t.pnl or 0) <= 0)
                win_rate = round(wins / total, 4) if total > 0 else 0.50
                avg_pnl = round(sum(float(t.pnl or 0) for t in trades) / total, 2) if total > 0 else 0.0

                gross_profit = sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) > 0)
                gross_loss = abs(sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) < 0))
                profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)

                self.strategy_performance[s.name] = {
                    "total_trades": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                    "avg_pnl": avg_pnl,
                    "profit_factor": profit_factor,
                }
        except Exception as exc:
            bot_logger.error(f"[Engine] Failed to initialize strategy performance: {exc}")
        finally:
            db.close()

    def _update_strategy_performance_on_close(self, strategy_name: str, pnl: float, db) -> None:
        """Update historical performance metrics for strategy_name after a closed trade."""
        if not strategy_name:
            return
        try:
            trades = db.query(Trade).filter(Trade.status == "CLOSED", Trade.strategy == strategy_name).all()
            total = len(trades)
            wins = sum(1 for t in trades if (t.pnl or 0) > 0)
            losses = sum(1 for t in trades if (t.pnl or 0) <= 0)
            win_rate = round(wins / total, 4) if total > 0 else 0.50
            avg_pnl = round(sum(float(t.pnl or 0) for t in trades) / total, 2) if total > 0 else 0.0

            gross_profit = sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) > 0)
            gross_loss = abs(sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) < 0))
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)

            self.strategy_performance[strategy_name] = {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "profit_factor": profit_factor,
            }
        except Exception as exc:
            bot_logger.error(f"[Engine] Error updating strategy performance for {strategy_name}: {exc}")

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """Start the trading engine."""
        self.running = True
        for s in self.strategies:
            s.enable()
        if self.mode == "live":
            try:
                db = SessionLocal()
                self.adopt_live_holdings(db)
                db.close()
            except Exception as ad_err:
                bot_logger.debug(f"[Engine] Could not auto-adopt holdings on start: {ad_err}")
        bot_logger.info(
            "TradingEngine STARTED [PRIME DIRECTIVE: Autonomous A-to-Z Agency | "
            "Zero Ruin Mandate: Capital preservation is existential. If capital is depleted, the bot is dead. "
            "Operate end-to-end to run successfully without losing capital.]"
        )

    def stop(self):
        """Stop the trading engine."""
        self.running = False
        bot_logger.info("TradingEngine STOPPED")

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------
    def run_cycle(self, pairs: List[str]) -> List[Dict[str, Any]]:
        """
        Execute one full trading cycle across all watched pairs.

        Steps:
          1. Check open trades for stop-loss, take-profit, and time-based exits.
          2. For each pair, fetch 15-minute candles.
          3. Run each enabled strategy's analyze() method.
          4. Collect, deconflict, regime-weight, and rank all signals.
          5. Validate with risk manager and execute approved signals via smart routing.
          6. Return a list of action summaries.

        Args:
            pairs: List of trading pair strings to scan (e.g. ['BTC/INR']).

        Returns:
            List of dicts summarising each action taken this cycle.
        """
        if not self.running:
            return []

        # Update position tracker mark-to-market
        try:
            current_prices = self.exchange_manager.get_current_prices()
            if current_prices:
                self.position_tracker.update_mark_to_market(current_prices)
        except Exception as e:
            bot_logger.debug(f"[Engine] MTM update failed: {e}")

        # Check existing positions first
        try:
            self.check_open_trades()
        except Exception as e:
            bot_logger.error(f"[Engine] Error in check_open_trades: {e}")

        actions_taken: List[Dict[str, Any]] = []
        all_signals: List[StrategySignal] = []
        detected_regimes: Dict[str, str] = {}
        recent_closes: Dict[str, pd.Series] = {}

        # ------------------------------------------------------------------
        # Phase 1: Collect signals from all strategies for every pair
        # ------------------------------------------------------------------
        for pair in pairs:
            try:
                df = self.exchange_manager.get_candles(
                    pair=pair, interval="15m", limit=100
                )
                if df is None or df.empty:
                    bot_logger.warning(
                        f"[Engine] No candle data for {pair}, skipping"
                    )
                    continue

                if "close" in df.columns:
                    recent_closes[pair] = df["close"]

                # Step 1.1: Market Regime Detection
                try:
                    regime_res = self.regime_detector.detect(pair, df)
                    detected_regimes[pair] = regime_res.get("regime", "NEUTRAL")
                except Exception as reg_err:
                    bot_logger.warning(f"[Engine] Regime detector error on {pair}: {reg_err}")
                    detected_regimes[pair] = "NEUTRAL"

                # Step 1.2: Run each enabled strategy
                for strategy in self.strategies:
                    if not strategy.enabled:
                        continue
                    try:
                        signal = strategy.analyze(df, pair)
                        if signal is not None and signal.action != "HOLD":
                            all_signals.append(signal)
                    except Exception as e:
                        bot_logger.error(
                            f"[Engine] Strategy {strategy.name} error on "
                            f"{pair}: {e}"
                        )
            except Exception as e:
                bot_logger.error(
                    f"[Engine] Failed to fetch data for {pair}: {e}"
                )

        # Update cross-asset correlation matrix (Agent 4)
        if len(recent_closes) >= 2 and hasattr(self.risk_manager, "correlation_manager"):
            try:
                self.risk_manager.correlation_manager.update_correlation_matrix(recent_closes)
            except Exception as ce:
                bot_logger.debug(f"[Engine] Correlation matrix update error: {ce}")

        # ------------------------------------------------------------------
        # Phase 1.5: Aggregate, deconflict, regime-weight, and rank signals
        # ------------------------------------------------------------------
        win_rates = {
            strat_name: stats.get("win_rate", 0.50)
            for strat_name, stats in self.strategy_performance.items()
        }
        aggregated_signals = self.signal_aggregator.aggregate(
            signals=all_signals,
            regime="NEUTRAL",
            win_rates=win_rates,
            pair_regimes=detected_regimes,
            enforce_throttle=True,
        )

        if all_signals:
            bot_logger.info(
                f"[Engine] SignalAggregator: {len(all_signals)} raw signals aggregated down to "
                f"{len(aggregated_signals)} actionable deconflicted signals"
            )

        # ------------------------------------------------------------------
        # Phase 2: Process filtered signals through risk management and execute
        # ------------------------------------------------------------------
        db = SessionLocal()
        try:
            for signal in aggregated_signals:
                try:
                    action = self._process_signal(signal, db)
                    if action is not None:
                        actions_taken.append(action)
                except Exception as e:
                    bot_logger.error(
                        f"[Engine] Signal processing error: {e}"
                    )
        finally:
            db.close()

        self._last_cycle_time = timestamp_now()
        self._total_cycles += 1

        if actions_taken:
            bot_logger.info(
                f"[Engine] Cycle #{self._total_cycles} complete: "
                f"{len(actions_taken)} actions from {len(all_signals)} signals"
            )
        return actions_taken

    def _process_signal(
        self, signal: StrategySignal, db
    ) -> Optional[Dict[str, Any]]:
        """
        Validate a signal through risk management and execute if approved.

        Returns an action-summary dict, or None if the signal was rejected.
        """
        pair = signal.pair
        action = signal.action

        # -- Persist the signal first --
        self._save_signal(signal, db)

        # -- Shadow Mode Guard --
        if bool(signal.metadata and signal.metadata.get("shadow_mode")):
            bot_logger.info(
                f"[Engine] [SHADOW MODE] {signal.strategy} {action} signal on {pair} "
                f"(confidence={signal.strength:.2f}) recorded to DB — trade execution bypassed."
            )
            return {
                "pair": pair,
                "action": action,
                "strategy": signal.strategy,
                "strength": signal.strength,
                "shadow_mode": True,
                "executed": False,
                "reason": signal.reason,
                "metadata": signal.metadata,
                "timestamp": timestamp_now(),
            }

        # -- Pre-Trade Risk Gate (Agent 4) --
        if action == "BUY":
            current_prices = self.exchange_manager.get_current_prices()
            if self.mode == "live":
                from backend.api.portfolio import _get_live_holdings
                cash_inr, crypto_inr, _ = _get_live_holdings(self.exchange_manager)
                portfolio_value = cash_inr + crypto_inr
                if cash_inr < 50.0:
                    bot_logger.info(
                        f"[Engine] Live BUY for {pair} skipped: Available liquid INR cash (₹{cash_inr:.2f}) "
                        "is below exchange minimum order requirement. Capital is currently held in spot crypto assets."
                    )
                    return None
            else:
                portfolio_value = self.paper_trader.get_portfolio_value(current_prices)

            # Update portfolio monitor with latest mark-to-market equity
            if hasattr(self.risk_manager, "portfolio_monitor"):
                self.risk_manager.portfolio_monitor.update_portfolio_value(portfolio_value, engine=self)

            ticker = self.exchange_manager.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
            if current_price <= 0:
                bot_logger.warning(f"[Engine] Invalid ticker price for {pair}")
                return None

            # Gather open positions for risk gate
            open_positions = []
            if hasattr(self, "position_tracker"):
                open_positions = [p.to_dict() for p in self.position_tracker.get_all_positions()]
            else:
                open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
                open_positions = [
                    {"pair": t.pair, "side": t.side, "quantity": t.quantity, "entry_price": t.entry_price}
                    for t in open_trades
                ]

            strategy_stats = self.strategy_performance.get(signal.strategy, {})

            decision = self.risk_manager.validate_signal(
                signal=signal,
                portfolio_value=portfolio_value,
                open_positions=open_positions,
                db_session=db,
                current_price=current_price,
                strategy_stats=strategy_stats,
            )

            if not decision.approved:
                bot_logger.info(
                    f"[Engine] Signal for {pair} rejected by Pre-Trade Risk Gate: {'; '.join(decision.reasons)}"
                )
                return None

            act_signal = decision.adjusted_signal or signal
            position_size = decision.position_size

            stop_loss = act_signal.metadata.get("stop_loss_price") if act_signal.metadata else None
            take_profit = act_signal.metadata.get("take_profit_price") if act_signal.metadata else None
            if not stop_loss:
                stop_loss = self.risk_manager.calculate_stop_loss(current_price, "BUY")
            if not take_profit:
                take_profit = self.risk_manager.calculate_take_profit(current_price, "BUY")

            # Execute the trade via smart order routing
            trade_result = self._execute_trade(
                pair=pair,
                side="BUY",
                quantity=position_size,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal=act_signal,
            )

            if trade_result:
                # In paper mode, PaperTrader already wrote the Trade row to the DB.
                # Only persist separately for live trades.
                if self.mode != "paper":
                    self._save_trade(trade_result, signal, db)
                return trade_result

        elif action == "SELL":
            # For SELL, close existing positions for this pair
            ticker = self.exchange_manager.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
            if current_price <= 0:
                return None

            open_trades = (
                db.query(Trade)
                .filter(Trade.status == "OPEN", Trade.pair == pair)
                .all()
            )

            actions = []
            for trade in open_trades:
                try:
                    self._close_trade_internal(trade, current_price, "STRATEGY_SELL", db)
                    actions.append({"id": trade.id, "pair": pair, "side": "SELL", "price": current_price})
                except Exception as e:
                    bot_logger.error(f"[Engine] Failed to close trade {trade.id} on SELL signal: {e}")

            if actions:
                return {"message": f"Closed {len(actions)} trades on SELL signal", "actions": actions}

            return None

    def _execute_trade(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        signal: StrategySignal,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a trade using smart order routing in paper or live mode.
        Tracks execution metrics (slippage, fill time, partial fills) and
        updates the unified position tracker.
        """
        start_time = time.time()
        try:
            # Step 1: Fetch order book to inspect liquidity depth
            order_book = None
            try:
                order_book = self.exchange_manager.get_order_book(pair=pair, limit=20)
            except Exception as ob_err:
                bot_logger.debug(f"[Engine] Could not fetch order book for {pair}: {ob_err}")

            market_state = {
                "current_price": price,
                "order_book": order_book,
                "quantity": quantity,
            }

            # Step 2: Route order through SmartOrderRouter
            plans = self.order_router.route(signal=signal, market_state=market_state, quantity=quantity)
            if not plans:
                plans = [
                    OrderPlan(
                        order_type="MARKET",
                        quantity=quantity,
                        price=price,
                        delay_seconds=0.0,
                        timeout_seconds=15.0,
                        fallback="MARKET",
                    )
                ]

            executed_results = []
            filled_tranches: List[Dict[str, float]] = []
            had_partial = False

            # Step 3: Execute routed plans
            if self.mode == "paper":
                for plan in plans:
                    exec_price = plan.price if plan.price and plan.price > 0 else price
                    res = self.paper_trader.execute_trade_with_slippage(
                        pair=pair,
                        side=side,
                        quantity=plan.quantity,
                        price=exec_price,
                        strategy=signal.strategy,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        entry_reason=signal.reason if signal else "Strategy trade",
                        order_type=plan.order_type,
                        timeout_seconds=plan.timeout_seconds,
                    )
                    if isinstance(res, dict) and "error" not in res:
                        executed_results.append(res)
                        filled_tranches.append({
                            "qty": plan.quantity,
                            "price": res.get("entry_price", exec_price),
                        })
                        if res.get("had_partial_fills"):
                            had_partial = True
                    else:
                        bot_logger.warning(f"[Engine] Paper execution plan failed: {res}")
            else:
                # Live execution with smart order routing & fill polling
                import threading
                for idx, plan in enumerate(plans):
                    rounded_plan_qty = self.exchange_manager.round_quantity(pair, plan.quantity)
                    exec_price = plan.price if plan.price and plan.price > 0 else price

                    if plan.delay_seconds > 0:
                        # Offload delayed TWAP chunks to background daemon thread (never block main engine cycle)
                        def _run_delayed(p=plan, rq=rounded_plan_qty, ep=exec_price):
                            try:
                                time.sleep(p.delay_seconds)
                                self.exchange_manager.place_order(
                                    pair=pair,
                                    side=side,
                                    quantity=rq,
                                    price=ep,
                                    order_type=p.order_type,
                                )
                                bot_logger.info(f"[Engine] Delayed TWAP chunk executed: {side} {rq} {pair} @ ₹{ep:.2f}")
                            except Exception as ex:
                                bot_logger.error(f"[Engine] Delayed TWAP chunk failed: {ex}")
                        threading.Thread(target=_run_delayed, daemon=True).start()
                        continue

                    order_res = self.exchange_manager.place_order(
                        pair=pair,
                        side=side,
                        quantity=rounded_plan_qty,
                        price=exec_price,
                        order_type=plan.order_type,
                    )

                    # Validate exchange response
                    if (
                        not isinstance(order_res, dict)
                        or "error" in order_res
                        or order_res.get("status") in ("rejected", "failed")
                    ):
                        err_msg = order_res.get("error") if isinstance(order_res, dict) else str(order_res)
                        bot_logger.error(f"[Engine] Live order placement rejected for {pair}: {err_msg}")
                        continue

                    order_id = order_res.get("id") or order_res.get("order_id")
                    filled_qty = rounded_plan_qty
                    fill_price = exec_price

                    # If limit order and order_id present, poll for fill
                    if order_id and plan.order_type.upper() == "LIMIT":
                        poll_start = time.time()
                        status = "open"
                        while time.time() - poll_start < plan.timeout_seconds:
                            time.sleep(0.5)
                            try:
                                status_res = self.exchange_manager.get_order_status(order_id)
                                if isinstance(status_res, dict):
                                    status = status_res.get("status", "open").lower()
                                    if status in ["filled", "closed", "complete"]:
                                        fill_price = float(status_res.get("price") or exec_price)
                                        filled_qty = float(status_res.get("filled_quantity") or rounded_plan_qty)
                                        break
                            except Exception:
                                pass

                        # If timed out and still open, cancel and fallback to MARKET if specified
                        if status not in ["filled", "closed", "complete"]:
                            had_partial = True
                            bot_logger.warning(
                                f"[Engine] Limit order {order_id} timed out after {plan.timeout_seconds}s. Cancelling..."
                            )
                            try:
                                self.exchange_manager.cancel_order(order_id)
                            except Exception as ce:
                                bot_logger.warning(f"[Engine] Cancel order error: {ce}")

                            if plan.fallback.upper() == "MARKET":
                                bot_logger.info(f"[Engine] Fallback: Executing MARKET order for {rounded_plan_qty} {pair}")
                                fb_res = self.exchange_manager.place_order(
                                    pair=pair,
                                    side=side,
                                    quantity=rounded_plan_qty,
                                    price=price,
                                    order_type="MARKET",
                                )
                                executed_results.append(fb_res)

                    executed_results.append(order_res)
                    filled_tranches.append({"qty": filled_qty, "price": fill_price})

            # Check if any tranche actually succeeded
            if not filled_tranches:
                bot_logger.error(f"[Engine] No order tranches succeeded for {pair}. Aborting trade registration.")
                return None

            # Calculate execution metrics
            total_filled = sum(t["qty"] for t in filled_tranches)
            weighted_fill_price = (
                sum(t["qty"] * t["price"] for t in filled_tranches) / max(total_filled, 1e-9)
                if filled_tranches else price
            )
            slippage_bps = (
                round(abs(weighted_fill_price - price) / price * 10000.0, 2)
                if price > 0 else 0.0
            )
            fill_time_ms = round((time.time() - start_time) * 1000.0, 2)

            primary_res = executed_results[0] if executed_results else {}
            trade_id = primary_res.get("id") if isinstance(primary_res, dict) else None

            # Step 4: Register in Unified Position Tracker
            pos = self.position_tracker.open_position({
                "pair": pair,
                "side": side,
                "quantity": total_filled,
                "price": weighted_fill_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "strategy": signal.strategy,
                "trade_id": trade_id,
            })

            trade_info = {
                "id": trade_id,
                "pair": pair,
                "side": side,
                "quantity": total_filled,
                "price": round(weighted_fill_price, 4),
                "requested_price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "strategy": signal.strategy,
                "strength": signal.strength,
                "reason": signal.reason,
                "mode": self.mode,
                "timestamp": timestamp_now(),
                "execution_metrics": {
                    "fill_time_ms": fill_time_ms,
                    "total_filled": round(total_filled, 6),
                    "avg_fill_price": round(weighted_fill_price, 4),
                    "slippage_bps": slippage_bps,
                    "had_partial_fills": had_partial,
                    "num_orders": len(plans),
                    "plans": [p.to_dict() for p in plans],
                },
                "result": primary_res,
            }

            bot_logger.info(
                f"[Engine] Trade executed: {side} {total_filled:.6f} {pair} @ "
                f"₹{weighted_fill_price:.2f} (slip: {slippage_bps} bps, {fill_time_ms}ms) | "
                f"strategy={signal.strategy} | mode={self.mode}"
            )
            return trade_info

        except Exception as e:
            bot_logger.error(
                f"[Engine] Trade execution failed for {pair}: {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Spot Holdings Auto-Adoption & Rebalance
    # ------------------------------------------------------------------
    def adopt_live_holdings(self, db) -> List[Dict[str, Any]]:
        """
        Auto-adopt unmanaged exchange spot balances into tracked open trades.
        Ensures existing spot crypto (e.g. XRP, SHIB in CoinDCX) is guarded
        by active trailing stop-losses and take-profit targets, and sold
        when strategy exit signals trigger.
        """
        if self.mode != "live" or not self.exchange_manager:
            return []

        adopted = []
        try:
            balances = self.exchange_manager.get_balances()
            for curr, data in balances.items():
                if curr == "INR":
                    continue
                avail = float(data.get("available", 0) or 0)
                if avail <= 0:
                    continue

                pair = f"{curr}/INR"
                ticker = self.exchange_manager.get_ticker(pair)
                current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
                if current_price <= 0:
                    continue

                val_inr = avail * current_price
                # Only adopt if notional value is at least ₹20
                if val_inr < 20.0:
                    continue

                # Check if there's already an OPEN trade for this pair in live mode
                existing = (
                    db.query(Trade)
                    .filter(Trade.status == "OPEN", Trade.pair == pair, Trade.paper_mode == False)
                    .first()
                )
                if existing:
                    continue

                # Adopt as a managed trade with tight capital preservation controls
                stop_loss = round(current_price * 0.98, 4)  # 2.0% protective stop
                take_profit = round(current_price * 1.035, 4)  # 3.5% take profit target
                trailing_stop = round(current_price * 0.985, 4)

                trade = Trade(
                    pair=pair,
                    side="BUY",
                    quantity=avail,
                    entry_price=round(current_price, 4),
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    trailing_stop=trailing_stop,
                    strategy="Asset_Guardian",
                    status="OPEN",
                    paper_mode=False,
                    created_at=datetime.utcnow(),
                    entry_reason=f"Auto-adopted {avail} {curr} (~₹{val_inr:.2f}) from CoinDCX spot wallet",
                )
                db.add(trade)
                db.commit()
                db.refresh(trade)

                if hasattr(self, "position_tracker"):
                    self.position_tracker.open_position({
                        "pair": pair,
                        "side": "BUY",
                        "quantity": avail,
                        "price": current_price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "strategy": "Asset_Guardian",
                        "trade_id": trade.id,
                    })

                bot_logger.info(
                    f"[Engine] Auto-adopted live spot holding: {avail} {curr} (~₹{val_inr:.2f}) @ ₹{current_price} "
                    f"with SL=₹{stop_loss} and TP=₹{take_profit}"
                )
                adopted.append({
                    "id": trade.id,
                    "currency": curr,
                    "pair": pair,
                    "quantity": avail,
                    "value_inr": round(val_inr, 2),
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                })
        except Exception as e:
            bot_logger.warning(f"[Engine] Error adopting live holdings: {e}")

        return adopted

    def rebalance_holdings_to_cash(self, db) -> List[Dict[str, Any]]:
        """
        Execute market SELL orders on CoinDCX for all held spot crypto
        (e.g. XRP, SHIB) to convert them into liquid INR cash capital.
        """
        if self.mode != "live" or not self.exchange_manager:
            return []

        sold_list = []
        balances = self.exchange_manager.get_balances()
        for curr, data in balances.items():
            if curr == "INR":
                continue
            avail = float(data.get("available", 0) or 0)
            if avail <= 0:
                continue

            pair = f"{curr}/INR"
            rounded_qty = self.exchange_manager.round_quantity(pair, avail)
            if rounded_qty <= 0:
                continue

            ticker = self.exchange_manager.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)

            order_res = self.exchange_manager.place_order(
                pair=pair,
                side="SELL",
                quantity=rounded_qty,
                price=current_price,
                order_type="MARKET",
            )
            # Close any existing open trade in DB for this pair
            open_trades = db.query(Trade).filter(Trade.status == "OPEN", Trade.pair == pair, Trade.paper_mode == False).all()
            for t in open_trades:
                t.status = "CLOSED"
                t.closed_at = datetime.utcnow()
                t.exit_price = current_price
                t.exit_reason = "REBALANCE_TO_CASH"
                t.pnl = 0.0
            db.commit()

            sold_list.append({
                "currency": curr,
                "pair": pair,
                "quantity": rounded_qty,
                "order_result": order_res,
            })
            bot_logger.info(f"[Engine] Rebalanced {rounded_qty} {curr} to INR cash via CoinDCX market sell.")

        return sold_list

    # ------------------------------------------------------------------
    # Open trade management
    # ------------------------------------------------------------------
    def check_open_trades(self):
        """
        Check all open trades for stop-loss, take-profit, or trailing-stop
        triggers. Close trades that meet exit criteria.
        """
        if not self.running:
            return

        # Synchronize mark-to-market prices on PositionTracker
        if hasattr(self, "position_tracker") and hasattr(self, "exchange_manager"):
            try:
                current_prices = self.exchange_manager.get_current_prices()
                if current_prices:
                    self.position_tracker.update_mark_to_market(current_prices)
            except Exception as e:
                bot_logger.debug(f"[Engine] MTM update failed: {e}")

        db = SessionLocal()
        try:
            if self.mode == "live":
                try:
                    self.adopt_live_holdings(db)
                except Exception as ad_err:
                    bot_logger.debug(f"[Engine] Auto-adopt in check_open_trades error: {ad_err}")

            is_paper = (self.mode == "paper")
            open_trades = (
                db.query(Trade)
                .filter(Trade.status == "OPEN", Trade.paper_mode == is_paper)
                .all()
            )

            for trade in open_trades:
                try:
                    self._check_single_trade(trade, db)
                except Exception as e:
                    bot_logger.error(
                        f"[Engine] Error checking trade {trade.id}: {e}"
                    )
        finally:
            db.close()

    def _check_single_trade(self, trade, db):
        """Check a single open trade for exit conditions."""
        ticker = self.exchange_manager.get_ticker(trade.pair)
        if not ticker:
            return

        current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
        if current_price <= 0:
            return

        # 1. Scalping Time-based exit check (max 300s = 5m hold time)
        if trade.strategy == "Scalping" and trade.created_at:
            now_utc = datetime.utcnow()
            hold_time_sec = (now_utc - trade.created_at).total_seconds()
            if hold_time_sec > 300:
                bot_logger.info(
                    f"[Engine] Scalping trade #{trade.id} reached max hold time "
                    f"({hold_time_sec:.0f}s > 300s). Triggering MAX_HOLD_TIME exit."
                )
                self._close_trade_internal(trade, current_price, "MAX_HOLD_TIME", db)
                return

        # 2. Grid Trading Rebalance exit check (dev >= 5.0% from entry price)
        if trade.strategy == "Grid_Trading" and trade.entry_price:
            dev_pct = abs(current_price - trade.entry_price) / max(trade.entry_price, 1e-9) * 100.0
            if dev_pct >= 5.0:
                bot_logger.info(
                    f"[Engine] Grid_Trading trade #{trade.id} reached rebalance threshold "
                    f"({dev_pct:.2f}% >= 5.0%). Triggering GRID_REBALANCE exit."
                )
                self._close_trade_internal(trade, current_price, "GRID_REBALANCE", db)
                return

        # 3. Update trailing stop if applicable
        new_trailing_stop = self.risk_manager.update_trailing_stop(
            trade=trade,
            current_price=current_price,
        )
        if new_trailing_stop:
            trade.trailing_stop = new_trailing_stop
            if hasattr(self, "position_tracker"):
                self.position_tracker.update_trailing_stop(trade.pair, new_trailing_stop)
            db.commit()

        # 4. Check stop loss
        if self.risk_manager.should_stop_loss(trade=trade, current_price=current_price):
            self._close_trade_internal(
                trade, current_price, "STOP_LOSS", db
            )
            return

        # 5. Check take profit
        if self.risk_manager.should_take_profit(trade=trade, current_price=current_price):
            self._close_trade_internal(
                trade, current_price, "TAKE_PROFIT", db
            )
            return

    def _close_trade_internal(
        self, trade, exit_price: float, reason: str, db
    ):
        """Close a trade, calculate P&L, exit slippage, and update the database and position tracker."""
        entry_price = float(trade.entry_price)
        quantity = float(trade.quantity)
        requested_exit_price = exit_price
        actual_exit_price = exit_price

        # Execute the close on paper / live
        try:
            if self.mode == "paper":
                close_res = self.paper_trader.close_trade(
                    trade_id=trade.id,
                    current_price=exit_price,
                    exit_reason=reason,
                )
                if isinstance(close_res, dict) and "exit_price" in close_res:
                    actual_exit_price = float(close_res["exit_price"])
            else:
                rounded_close_qty = self.exchange_manager.round_quantity(trade.pair, quantity)
                close_order_res = self.exchange_manager.place_order(
                    pair=trade.pair,
                    side="SELL" if trade.side == "BUY" else "BUY",
                    quantity=rounded_close_qty,
                    price=exit_price,
                    order_type="MARKET",
                )
                if (
                    not isinstance(close_order_res, dict)
                    or "error" in close_order_res
                    or close_order_res.get("status") in ("rejected", "failed")
                ):
                    err_msg = close_order_res.get("error") if isinstance(close_order_res, dict) else str(close_order_res)
                    bot_logger.critical(
                        f"[Engine] Live close order failed for trade #{trade.id} ({trade.pair}): {err_msg}. "
                        "Trade will NOT be marked CLOSED in DB to prevent unmanaged open position risk."
                    )
                    try:
                        from backend.monitoring.alert_manager import alert_manager
                        alert_manager.send_alert(
                            title=f"Live Close Order Failed #{trade.id}",
                            message=f"Could not close {trade.side} {quantity} {trade.pair}: {err_msg}",
                            level="CRITICAL",
                        )
                    except Exception:
                        pass
                    return  # Abort closing trade in DB!
        except Exception as e:
            bot_logger.critical(
                f"[Engine] Failed to execute close order for trade #{trade.id}: {e}. "
                "Trade will NOT be marked CLOSED in DB to prevent unmanaged position risk."
            )
            return

        exit_slippage_bps = (
            round(abs(actual_exit_price - requested_exit_price) / max(requested_exit_price, 1e-9) * 10000.0, 2)
            if requested_exit_price > 0 else 0.0
        )

        pnl = calculate_pnl(entry_price, actual_exit_price, quantity, trade.side)
        pnl_pct = calculate_pnl_pct(entry_price, actual_exit_price, trade.side)

        trade.exit_price = actual_exit_price
        trade.pnl = round(pnl, 2)
        trade.status = "CLOSED"
        trade.closed_at = datetime.utcnow()
        trade.exit_reason = reason

        db.commit()

        # Update Unified Position Tracker
        if hasattr(self, "position_tracker"):
            self.position_tracker.close_position(
                pair=trade.pair,
                exit_price=actual_exit_price,
                reason=reason,
            )

        # Update per-strategy performance tracking metrics
        self._update_strategy_performance_on_close(trade.strategy, pnl, db)

        # Notify Strategy Performance Tracker (Agent 5)
        try:
            from backend.monitoring.strategy_tracker import strategy_tracker
            strategy_tracker.record_closed_trade(trade)
        except Exception as st_err:
            bot_logger.debug(f"[Engine] strategy_tracker record error: {st_err}")

        # Notify Risk Manager on trade close for win/loss streak and drawdown tracking (Agent 4)
        if hasattr(self.risk_manager, "on_trade_closed"):
            self.risk_manager.on_trade_closed(trade, engine=self)

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        bot_logger.info(
            f"[Engine] {pnl_emoji} Trade #{trade.id} CLOSED ({reason}): "
            f"{trade.pair} entry=₹{entry_price:.2f} exit=₹{actual_exit_price:.2f} "
            f"(slip: {exit_slippage_bps} bps) P&L=₹{pnl:.2f} ({pnl_pct:+.2f}%)"
        )

        # Self-learning reinforcement: Neural network adapts its weights based on trade outcome
        if trade.strategy and trade.strategy.startswith("Neural_Network"):
            for s in self.strategies:
                if s.name == trade.strategy and hasattr(s, "learn_from_trade"):
                    try:
                        s.learn_from_trade(trade, pnl_pct)
                    except Exception as exc:
                        bot_logger.error(f"[Engine] Neural Net reinforcement error: {exc}")
                    break

    def close_trade(self, trade_id: int, reason: str = "MANUAL"):
        """
        Manually close a specific trade by ID.

        Args:
            trade_id: Database ID of the trade to close.
            reason: Reason string (e.g. 'MANUAL', 'STRATEGY_EXIT').
        """
        db = SessionLocal()
        try:
            trade = db.query(Trade).filter(Trade.id == trade_id).first()
            if not trade:
                bot_logger.warning(
                    f"[Engine] Trade {trade_id} not found"
                )
                return
            if trade.status != "OPEN":
                bot_logger.warning(
                    f"[Engine] Trade {trade_id} is already {trade.status}"
                )
                return

            ticker = self.exchange_manager.get_ticker(trade.pair)
            current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
            if current_price <= 0:
                bot_logger.error(
                    f"[Engine] Cannot get price to close trade {trade_id}"
                )
                return

            self._close_trade_internal(trade, current_price, reason, db)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _save_signal(self, signal: StrategySignal, db):
        """Persist a strategy signal to the database."""
        try:
            metadata = dict(signal.metadata or {})
            metadata["reason"] = signal.reason
            db_signal = Signal(
                pair=signal.pair,
                signal_type=signal.action,
                strategy=signal.strategy,
                strength=signal.strength,
                metadata_json=json.dumps(metadata),
                created_at=timestamp_now(),
            )
            db.add(db_signal)
            db.commit()
        except Exception as e:
            db.rollback()
            bot_logger.error(f"[Engine] Failed to save signal: {e}")

    def _save_trade(
        self, trade_info: Dict[str, Any], signal: StrategySignal, db
    ):
        """Persist an executed trade to the database."""
        try:
            db_trade = Trade(
                pair=trade_info["pair"],
                side=trade_info["side"],
                entry_price=trade_info["price"],
                quantity=trade_info["quantity"],
                stop_loss=trade_info["stop_loss"],
                take_profit=trade_info["take_profit"],
                strategy=signal.strategy,
                status="OPEN" if trade_info["side"] == "BUY" else "CLOSED",
                paper_mode=(self.mode == "paper"),
                created_at=datetime.utcnow(),
                entry_reason=signal.reason if signal else None,
            )
            db.add(db_trade)
            db.commit()
            db.refresh(db_trade)

            if hasattr(self, "position_tracker"):
                self.position_tracker.open_position({
                    "pair": db_trade.pair,
                    "side": db_trade.side,
                    "quantity": db_trade.quantity,
                    "price": db_trade.entry_price,
                    "stop_loss": db_trade.stop_loss,
                    "take_profit": db_trade.take_profit,
                    "strategy": db_trade.strategy,
                    "trade_id": db_trade.id,
                })
        except Exception as e:
            db.rollback()
            bot_logger.error(f"[Engine] Failed to save trade: {e}")

    # ------------------------------------------------------------------
    # Strategy configuration
    # ------------------------------------------------------------------
    def get_strategies_config(self) -> Dict[str, Dict[str, Any]]:
        """Return configuration dicts for all registered strategies, keyed by name."""
        return {s.name: s.get_config() for s in self.strategies}

    def update_strategy_config(self, name: str, update: dict):
        """
        Update a strategy's enabled flag and/or parameters.

        Args:
            name: Strategy name to update.
            update: Dict that may contain 'enabled' (bool) and/or
                    'params' (dict of parameter values to merge).
        """
        for strategy in self.strategies:
            if strategy.name == name:
                if "enabled" in update and update["enabled"] is not None:
                    if update["enabled"]:
                        strategy.enable()
                    else:
                        strategy.disable()
                if "params" in update and update["params"]:
                    strategy.update_params(update["params"])
                bot_logger.info(
                    f"[Engine] Updated strategy {name}: {update}"
                )
                return
        raise ValueError(f"Strategy '{name}' not found")

    def enable_strategy(self, name: str):
        """Enable a strategy by name."""
        for strategy in self.strategies:
            if strategy.name == name:
                strategy.enable()
                bot_logger.info(f"[Engine] Strategy {name} ENABLED")
                return

    def disable_strategy(self, name: str):
        """Disable a strategy by name."""
        for strategy in self.strategies:
            if strategy.name == name:
                strategy.disable()
                bot_logger.info(f"[Engine] Strategy {name} DISABLED")
                return

    def reset_paper_account(self, new_balance: Optional[float] = None) -> Dict[str, Any]:
        """
        Paper Trading Reset Workflow:
        1. Verifies engine is in paper trading mode.
        2. Closes all active open positions at current market prices.
        3. Trains all Neural Network strategies on historical & closed trades.
        4. Deletes paper trades and portfolio snapshots from database.
        5. Resets cash balance to initial capital (settings.PAPER_BALANCE or new_balance).
        6. Clears position trackers and resets portfolio risk monitors.
        """
        if self.mode != "paper":
            raise ValueError("Reset operation is strictly forbidden in live trading mode.")

        db = SessionLocal()
        try:
            # 1. Close all active open positions
            open_trades = db.query(Trade).filter(Trade.status == "OPEN", Trade.paper_mode.is_(True)).all()
            closed_trades_count = 0
            for trade in open_trades:
                cur_price = float(trade.entry_price or 1.0)
                if hasattr(self, "exchange_manager"):
                    try:
                        ticker = self.exchange_manager.get_ticker(trade.pair)
                        cur_price = float(ticker.get("last_price", cur_price)) if isinstance(ticker, dict) else float(ticker)
                    except Exception:
                        pass
                if hasattr(self, "paper_trader"):
                    self.paper_trader.close_trade(trade.id, cur_price, exit_reason="PAPER_RESET")
                closed_trades_count += 1

            # Commit closed trades
            db.commit()

            # 2. Train neural networks on all closed trades
            all_closed_trades = db.query(Trade).filter(Trade.status == "CLOSED", Trade.paper_mode.is_(True)).all()
            total_history_trades = len(all_closed_trades)
            training_results = {}
            neural_strategies = [s for s in self.strategies if s.name.startswith("Neural_Network")]
            for strat in neural_strategies:
                try:
                    res = strat.train_on_closed_trades(
                        db=db,
                        exchange_manager=getattr(self, "exchange_manager", None),
                        epochs=25,
                    )
                    training_results[strat.name] = res
                except Exception as err:
                    training_results[strat.name] = {"status": "error", "error": str(err)}

            # 3. Purge paper trades and snapshots from database
            deleted_trades = db.query(Trade).filter(Trade.paper_mode.is_(True)).delete()
            deleted_snaps = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.paper_mode.is_(True)).delete()
            db.commit()

            # 4. Reset paper trader balance and clear in-memory positions
            initial_cap = float(new_balance or settings.PAPER_BALANCE)
            if hasattr(self, "paper_trader"):
                self.paper_trader.initial_balance = initial_cap
                self.paper_trader.balance = initial_cap
                self.paper_trader.positions.clear()

            # 5. Clear unified position tracker
            if hasattr(self, "position_tracker"):
                self.position_tracker.positions.clear()

            # 6. Reset portfolio risk monitor & cooldowns
            if hasattr(self, "risk_manager") and hasattr(self.risk_manager, "portfolio_monitor"):
                pm = self.risk_manager.portfolio_monitor
                pm.high_water_mark = initial_cap
                pm.current_drawdown_pct = 0.0
                pm.consecutive_losses = 0
                pm.consecutive_wins = 0
                pm.cooldown_until = None
                pm.trading_enabled = True

            # 7. Add fresh initial portfolio snapshot
            initial_snap = PortfolioSnapshot(
                total_value=initial_cap,
                cash=initial_cap,
                positions_json="[]",
                paper_mode=True,
                created_at=datetime.utcnow(),
            )
            db.add(initial_snap)
            db.commit()

            bot_logger.info(
                f"[Engine] Paper account reset complete: Closed {closed_trades_count} active trades, "
                f"trained NN on {total_history_trades} trades, purged {deleted_trades} DB records, "
                f"restored initial balance to {format_inr(initial_cap)}."
            )

            return {
                "status": "success",
                "message": (
                    f"Paper trading reset successfully. Trained neural networks on {total_history_trades} trades, "
                    f"closed {closed_trades_count} active positions, and restored capital to {format_inr(initial_cap)}."
                ),
                "closed_active_trades": closed_trades_count,
                "trained_trades": total_history_trades,
                "purged_records": deleted_trades,
                "neural_training": training_results,
                "initial_balance": initial_cap,
                "current_balance": initial_cap,
            }
        except Exception as exc:
            db.rollback()
            bot_logger.error(f"[Engine] Paper account reset failed: {exc}")
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Status / info
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """Return a summary of the engine's current state."""
        return {
            "running": self.running,
            "mode": self.mode,
            "total_cycles": self._total_cycles,
            "last_cycle_time": self._last_cycle_time,
            "strategies": [
                {"name": s.name, "enabled": s.enabled}
                for s in self.strategies
            ],
            "open_positions_count": len(self.position_tracker.positions) if hasattr(self, "position_tracker") else 0,
            "total_exposure": self.position_tracker.get_total_exposure() if hasattr(self, "position_tracker") else 0.0,
        }
