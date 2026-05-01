/**
 * Available technical indicators for the strategy builder.
 *
 * Each indicator defines its name, display label, default parameters,
 * and parameter schema for the UI form.
 */

export interface IndicatorParam {
  key: string;
  label: string;
  type: 'number' | 'select';
  default: number | string;
  min?: number;
  max?: number;
  step?: number;
  options?: { label: string; value: string | number }[];
}

export interface IndicatorDefinition {
  id: string;
  name: string;
  label: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume';
  description: string;
  params: IndicatorParam[];
  /** Output column names (relative to the indicator id) */
  outputs: string[];
  icon: string; // Emoji or icon name
}

export const INDICATORS: IndicatorDefinition[] = [
  // --- Trend ---
  {
    id: 'sma',
    name: 'sma',
    label: 'Simple Moving Average',
    category: 'trend',
    description: 'Average price over N periods. Classic trend filter.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 20, min: 2, max: 500, step: 1 },
    ],
    outputs: ['value'],
    icon: '📈',
  },
  {
    id: 'ema',
    name: 'ema',
    label: 'Exponential Moving Average',
    category: 'trend',
    description: 'Weighted average giving more importance to recent prices.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 20, min: 2, max: 500, step: 1 },
    ],
    outputs: ['value'],
    icon: '📊',
  },
  {
    id: 'wma',
    name: 'wma',
    label: 'Weighted Moving Average',
    category: 'trend',
    description: 'Linear-weighted moving average.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 20, min: 2, max: 500, step: 1 },
    ],
    outputs: ['value'],
    icon: '📉',
  },
  {
    id: 'macd',
    name: 'macd',
    label: 'MACD',
    category: 'trend',
    description: 'Moving Average Convergence Divergence — trend and momentum.',
    params: [
      { key: 'fast_period', label: 'Fast Period', type: 'number', default: 12, min: 2, max: 100, step: 1 },
      { key: 'slow_period', label: 'Slow Period', type: 'number', default: 26, min: 5, max: 200, step: 1 },
      { key: 'signal_period', label: 'Signal Period', type: 'number', default: 9, min: 2, max: 50, step: 1 },
    ],
    outputs: ['line', 'signal', 'hist'],
    icon: '〰️',
  },

  // --- Momentum ---
  {
    id: 'rsi',
    name: 'rsi',
    label: 'RSI',
    category: 'momentum',
    description: 'Relative Strength Index — overbought/oversold oscillator (0-100).',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 14, min: 2, max: 100, step: 1 },
    ],
    outputs: ['value'],
    icon: '⚡',
  },
  {
    id: 'stochastic',
    name: 'stochastic',
    label: 'Stochastic Oscillator',
    category: 'momentum',
    description: 'Compares closing price to price range over N periods.',
    params: [
      { key: 'k_period', label: '%K Period', type: 'number', default: 14, min: 2, max: 100, step: 1 },
      { key: 'd_period', label: '%D Period', type: 'number', default: 3, min: 2, max: 20, step: 1 },
    ],
    outputs: ['k', 'd'],
    icon: '🔄',
  },
  {
    id: 'cci',
    name: 'cci',
    label: 'CCI',
    category: 'momentum',
    description: 'Commodity Channel Index — measures price deviation from mean.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 20, min: 5, max: 100, step: 1 },
    ],
    outputs: ['value'],
    icon: '📐',
  },
  {
    id: 'williams_r',
    name: 'williams_r',
    label: "Williams %R",
    category: 'momentum',
    description: 'Momentum indicator similar to Stochastic, range -100 to 0.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 14, min: 2, max: 100, step: 1 },
    ],
    outputs: ['value'],
    icon: '🎯',
  },

  // --- Volatility ---
  {
    id: 'bollinger',
    name: 'bollinger',
    label: 'Bollinger Bands',
    category: 'volatility',
    description: 'Price envelopes using standard deviations from moving average.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 20, min: 5, max: 100, step: 1 },
      { key: 'std_dev', label: 'Std Deviation', type: 'number', default: 2.0, min: 0.5, max: 4.0, step: 0.5 },
    ],
    outputs: ['upper', 'middle', 'lower'],
    icon: '🔔',
  },
  {
    id: 'atr',
    name: 'atr',
    label: 'ATR',
    category: 'volatility',
    description: 'Average True Range — measures market volatility.',
    params: [
      { key: 'period', label: 'Period', type: 'number', default: 14, min: 2, max: 100, step: 1 },
    ],
    outputs: ['value'],
    icon: '📏',
  },

  // --- Volume ---
  {
    id: 'obv',
    name: 'obv',
    label: 'On-Balance Volume',
    category: 'volume',
    description: 'Cumulative volume flow based on price direction.',
    params: [],
    outputs: ['value'],
    icon: '📦',
  },
  {
    id: 'vwap',
    name: 'vwap',
    label: 'VWAP',
    category: 'volume',
    description: 'Volume Weighted Average Price — institutional benchmark.',
    params: [],
    outputs: ['value'],
    icon: '💰',
  },
];

export const INDICATOR_CATEGORIES = [
  { key: 'trend', label: 'Trend', color: '#00E676' },
  { key: 'momentum', label: 'Momentum', color: '#1DE9B6' },
  { key: 'volatility', label: 'Volatility', color: '#FFB74D' },
  { key: 'volume', label: 'Volume', color: '#42A5F5' },
] as const;

export const getIndicatorById = (id: string): IndicatorDefinition | undefined =>
  INDICATORS.find((ind) => ind.id === id);

export default INDICATORS;
