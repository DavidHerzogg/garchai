/**
 * Client-side validation helpers for strategy forms.
 */

export function validateStrategyName(name: string): string | null {
  if (!name.trim()) return 'Strategy name is required';
  if (name.length < 2) return 'Name must be at least 2 characters';
  if (name.length > 100) return 'Name must be under 100 characters';
  return null;
}

export function validatePositionSize(value: number): string | null {
  if (value <= 0) return 'Position size must be positive';
  if (value > 100) return 'Position size cannot exceed 100%';
  return null;
}

export function validateStopLoss(value: number): string | null {
  if (value <= 0) return 'Stop loss must be positive';
  if (value > 50) return 'Stop loss of >50% is unreasonably large';
  return null;
}

export function validateTakeProfit(value: number): string | null {
  if (value <= 0) return 'Take profit must be positive';
  if (value > 1000) return 'Take profit of >1000% is unreasonably large';
  return null;
}

export function validateLookbackDays(value: number): string | null {
  if (value < 7) return 'Lookback must be at least 7 days';
  if (value > 3650) return 'Lookback cannot exceed 10 years';
  return null;
}

export function formatPercent(value: number, decimals: number = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
}

export function formatNumber(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
}
