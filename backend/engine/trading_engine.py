"""
AutoTrader Pro - Trading Engine Orchestrator
=============================================
Central orchestrator that coordinates all trading strategies, the exchange,
risk management, paper trading, and database persistence.

The engine's ``run_cycle()`` method is called periodically by the scheduler.
It fetches market data, runs every enabled strategy, validates signals
through the risk manager, executes trades (paper or live), and persists
everything to the database.
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import pandas as pd

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Trade, Signal
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now, calculate_pnl, calculate_pnl_pct

from backend.exchange.exchange_manager import ExchangeManager
from backend.risk.risk_manager import RiskManager
from backend.paper.paper_trader import PaperTrader

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.ma_pullback import MAPullbackStrategy
from backend.engine.breakout_hunter import BreakoutHunterStrategy
from backend.engine.rsi_divergence import RSIDivergenceStrategy
from backend.engine.sentiment_llm import SentimentLLMStrategy
from backend.engine.grid_trading import GridTradingStrategy


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

        # -- Strategies --
        self.strategies: List[StrategyBase] = [
            MAPullbackStrategy(),
            BreakoutHunterStrategy(),
            RSIDivergenceStrategy(),
            SentimentLLMStrategy(),
            GridTradingStrategy(),
        ]

        # -- Cycle stats --
        self._last_cycle_time: Optional[str] = None
        self._total_cycles: int = 0

        bot_logger.info(
            f"TradingEngine initialized — mode={self.mode}, "
            f"strategies={[s.name for s in self.strategies]}"
        )

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """Start the trading engine."""
        self.running = True
        bot_logger.info("TradingEngine STARTED")

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
          1. For each pair, fetch 15-minute candles.
          2. Run each enabled strategy's analyze() method.
          3. Collect all generated signals.
          4. For each actionable signal:
             a. Validate with risk manager.
             b. Calculate position size, stop-loss, take-profit.
             c. Execute trade via paper_trader or exchange_manager.
             d. Persist Trade and Signal to database.
          5. Return a list of action summaries.

        Args:
            pairs: List of trading pair strings to scan (e.g. ['BTC/INR']).

        Returns:
            List of dicts summarising each action taken this cycle.
        """
        if not self.running:
            return []

        actions_taken: List[Dict[str, Any]] = []
        all_signals: List[StrategySignal] = []

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

        # ------------------------------------------------------------------
        # Phase 2: Process signals through risk management and execute
        # ------------------------------------------------------------------
        db = SessionLocal()
        try:
            for signal in all_signals:
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

        # -- Risk checks --
        if action == "BUY":
            num_open_trades = (
                db.query(Trade).filter(Trade.status == "OPEN").count()
            )
            current_prices = self.exchange_manager.get_current_prices()
            portfolio_value = self.paper_trader.get_portfolio_value(current_prices)

            allowed, reason = self.risk_manager.can_open_trade(
                portfolio_value=portfolio_value,
                num_open_trades=num_open_trades,
            )
            if not allowed:
                bot_logger.info(
                    f"[Engine] Risk manager rejected new trade for {pair}: {reason}"
                )
                return None

            # Get current price for position sizing
            ticker = self.exchange_manager.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0)) if ticker else 0
            if current_price <= 0:
                bot_logger.warning(
                    f"[Engine] Invalid ticker price for {pair}"
                )
                return None

            position_size = self.risk_manager.calculate_position_size(
                portfolio_value=portfolio_value,
                entry_price=current_price,
            )
            stop_loss = self.risk_manager.calculate_stop_loss(
                entry_price=current_price, side="BUY"
            )
            take_profit = self.risk_manager.calculate_take_profit(
                entry_price=current_price, side="BUY"
            )

            # Use signal metadata stop loss if provided (e.g. from Breakout Hunter)
            if signal.metadata and "stop_loss_price" in signal.metadata:
                stop_loss = signal.metadata["stop_loss_price"]

            if position_size <= 0:
                bot_logger.warning(
                    f"[Engine] Calculated position size is zero for {pair}"
                )
                return None

            # Execute the trade
            trade_result = self._execute_trade(
                pair=pair,
                side="BUY",
                quantity=position_size,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal=signal,
            )

            if trade_result:
                # In paper mode, PaperTrader.execute_trade() already wrote
                # the Trade row to the DB — saving again here would create
                # a duplicate. Only persist separately for live trades.
                if self.mode != "paper":
                    self._save_trade(trade_result, signal, db)
                return trade_result

        elif action == "SELL":
            # For SELL, we close existing positions for this pair
            ticker = self.exchange_manager.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0)) if ticker else 0
            if current_price <= 0:
                return None

            open_trades = (
                db.query(Trade)
                .filter(
                    Trade.status == "OPEN",
                    Trade.pair == pair,
                    Trade.strategy == signal.strategy,
                )
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
        Execute a trade in paper or live mode.

        Returns a trade-result dict on success, None on failure.
        """
        try:
            if self.mode == "paper":
                result = self.paper_trader.execute_trade(
                    pair=pair,
                    side=side,
                    quantity=quantity,
                    price=price,
                    strategy=signal.strategy,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    entry_reason=signal.reason if signal else "Strategy trade",
                )
            else:
                result = self.exchange_manager.place_order(
                    pair=pair,
                    side=side,
                    quantity=quantity,
                    price=price,
                    order_type="LIMIT",
                )

            trade_info = {
                "pair": pair,
                "side": side,
                "quantity": quantity,
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "strategy": signal.strategy,
                "strength": signal.strength,
                "reason": signal.reason,
                "mode": self.mode,
                "timestamp": timestamp_now(),
                "result": result,
            }

            bot_logger.info(
                f"[Engine] Trade executed: {side} {quantity:.6f} {pair} @ "
                f"₹{price:.2f} | strategy={signal.strategy} | "
                f"mode={self.mode}"
            )
            return trade_info

        except Exception as e:
            bot_logger.error(
                f"[Engine] Trade execution failed for {pair}: {e}"
            )
            return None

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

        db = SessionLocal()
        try:
            open_trades = (
                db.query(Trade)
                .filter(Trade.status == "OPEN")
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

        current_price = float(ticker.get("last_price", 0))
        if current_price <= 0:
            return

        # Update trailing stop if applicable
        new_trailing_stop = self.risk_manager.update_trailing_stop(
            trade=trade,
            current_price=current_price,
        )
        if new_trailing_stop:
            trade.trailing_stop = new_trailing_stop
            db.commit()

        # Check stop loss
        if self.risk_manager.should_stop_loss(trade=trade, current_price=current_price):
            self._close_trade_internal(
                trade, current_price, "STOP_LOSS", db
            )
            return

        # Check take profit
        if self.risk_manager.should_take_profit(trade=trade, current_price=current_price):
            self._close_trade_internal(
                trade, current_price, "TAKE_PROFIT", db
            )
            return

    def _close_trade_internal(
        self, trade, exit_price: float, reason: str, db
    ):
        """Close a trade, calculate P&L, and update the database."""
        entry_price = float(trade.entry_price)
        quantity = float(trade.quantity)

        pnl = calculate_pnl(entry_price, exit_price, quantity, trade.side)
        pnl_pct = calculate_pnl_pct(entry_price, exit_price, trade.side)

        trade.exit_price = exit_price
        trade.pnl = pnl
        trade.status = "CLOSED"
        trade.closed_at = timestamp_now()
        trade.exit_reason = reason

        # Execute the close on paper / live
        try:
            if self.mode == "paper":
                self.paper_trader.close_trade(
                    trade_id=trade.id,
                    current_price=exit_price,
                    exit_reason=reason,
                )
            else:
                self.exchange_manager.place_order(
                    pair=trade.pair,
                    side="SELL",
                    quantity=quantity,
                    price=exit_price,
                    order_type="MARKET",
                )
        except Exception as e:
            bot_logger.error(
                f"[Engine] Failed to execute close order for "
                f"trade {trade.id}: {e}"
            )

        db.commit()

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        bot_logger.info(
            f"[Engine] {pnl_emoji} Trade {trade.id} CLOSED ({reason}): "
            f"{trade.pair} entry=₹{entry_price:.2f} exit=₹{exit_price:.2f} "
            f"P&L=₹{pnl:.2f} ({pnl_pct:+.2f}%)"
        )

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
            current_price = float(ticker.get("last_price", 0)) if ticker else 0
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
                created_at=trade_info["timestamp"],
            )
            db.add(db_trade)
            db.commit()
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
        }
