/**
 * Format a number as INR currency
 * @param {number} amount - The amount to format
 * @returns {string} Formatted INR string e.g., '₹10,000.00'
 */
export function formatINR(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0.00';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

/**
 * Format a compact INR value for large numbers
 * @param {number} amount
 * @returns {string} e.g., '₹1.2L' or '₹5.3Cr'
 */
export function formatINRCompact(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0';
  const abs = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
  return formatINR(amount);
}

/**
 * Format a percentage value with sign and color class
 * @param {number} value - Percentage value
 * @returns {{ text: string, colorClass: string }}
 */
export function formatPercent(value) {
  if (value === null || value === undefined || isNaN(value)) {
    return { text: '0.00%', colorClass: 'text-gray-400' };
  }
  const sign = value >= 0 ? '+' : '';
  const text = `${sign}${value.toFixed(2)}%`;
  const colorClass = value >= 0 ? 'text-neon-green' : 'text-neon-red';
  return { text, colorClass };
}

/**
 * Format a date string to readable format
 * @param {string|Date} date - Date to format
 * @returns {string} Formatted date e.g., 'Jun 16, 2026 12:30 PM'
 */
export function formatDate(date) {
  if (!date) return '—';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(d);
}

/**
 * Format a short date (no time)
 * @param {string|Date} date
 * @returns {string}
 */
export function formatShortDate(date) {
  if (!date) return '—';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(d);
}

/**
 * Format a time only
 * @param {string|Date} date
 * @returns {string}
 */
export function formatTime(date) {
  if (!date) return '—';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(d);
}

/**
 * Format a trading pair
 * @param {string} pair - e.g., 'BTCINR' or 'BTC_INR'
 * @returns {string} Formatted pair e.g., 'BTC/INR'
 */
export function formatPair(pair) {
  if (!pair) return '—';
  // If already has separator
  if (pair.includes('/')) return pair.toUpperCase();
  // Remove INR suffix and format
  const cleaned = pair.replace(/[_-]/g, '');
  if (cleaned.endsWith('INR')) {
    return `${cleaned.slice(0, -3)}/${cleaned.slice(-3)}`.toUpperCase();
  }
  return pair.toUpperCase();
}

/**
 * Get color class based on value
 * @param {number} value
 * @returns {string} Tailwind color class
 */
export function getChangeColor(value) {
  if (value === null || value === undefined || value === 0) return 'text-gray-400';
  return value > 0 ? 'text-neon-green' : 'text-neon-red';
}

/**
 * Get background color class based on value
 * @param {number} value
 * @returns {string}
 */
export function getChangeBg(value) {
  if (value === null || value === undefined || value === 0)
    return 'bg-gray-500/10 text-gray-400';
  return value > 0
    ? 'bg-neon-green/10 text-neon-green'
    : 'bg-neon-red/10 text-neon-red';
}

/**
 * Format duration from start time to now
 * @param {string|Date} startTime
 * @returns {string} e.g., '2h 30m' or '5m 20s'
 */
export function formatDuration(startTime) {
  if (!startTime) return '—';
  const start = new Date(startTime);
  const now = new Date();
  const diffMs = now - start;
  if (diffMs < 0) return '—';

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

/**
 * Clamp a number between min and max
 * @param {number} value
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
