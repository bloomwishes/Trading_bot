import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Animated counter component that smoothly transitions between values
 */
export default function AnimatedNumber({
  value = 0,
  duration = 800,
  prefix = '',
  suffix = '',
  decimals = 2,
  className = '',
  colorize = false,
}) {
  const [displayValue, setDisplayValue] = useState(value);
  const previousValue = useRef(value);
  const animationRef = useRef(null);
  const startTimeRef = useRef(null);

  const formatWithCommas = useCallback(
    (num) => {
      const fixed = Number(num).toFixed(decimals);
      const parts = fixed.split('.');
      // Use Indian numbering format for INR
      const intPart = parts[0].replace(/\B(?=(\d{2})+(?=\d{3})(?!\d))/g, ',');
      // Fallback to standard comma formatting
      const formatted = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return decimals > 0 ? `${formatted}.${parts[1]}` : formatted;
    },
    [decimals]
  );

  useEffect(() => {
    const from = previousValue.current;
    const to = value;

    if (from === to) return;

    // Cancel any running animation
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }

    startTimeRef.current = null;

    const animate = (timestamp) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);

      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = from + (to - from) * eased;

      setDisplayValue(current);

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        setDisplayValue(to);
        previousValue.current = to;
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value, duration]);

  // Update ref when value changes
  useEffect(() => {
    return () => {
      previousValue.current = value;
    };
  }, [value]);

  const colorClass = colorize
    ? value >= 0
      ? 'text-neon-green'
      : 'text-neon-red'
    : '';

  const sign = colorize && value > 0 ? '+' : '';

  return (
    <span className={`tabular-nums ${colorClass} ${className}`}>
      {sign}
      {prefix}
      {formatWithCommas(displayValue)}
      {suffix}
    </span>
  );
}
