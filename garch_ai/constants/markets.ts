/**
 * Available markets/symbols for the strategy builder.
 */

export interface MarketDefinition {
  symbol: string;
  label: string;
  category: 'crypto' | 'stock' | 'index' | 'commodity' | 'forex';
  icon: string;
  description: string;
  tradingHours: string;
}

export const MARKETS: MarketDefinition[] = [
  // --- Crypto ---
  { symbol: 'BTC-USD', label: 'Bitcoin', category: 'crypto', icon: '₿', description: 'Bitcoin / US Dollar', tradingHours: '24/7' },
  { symbol: 'ETH-USD', label: 'Ethereum', category: 'crypto', icon: 'Ξ', description: 'Ethereum / US Dollar', tradingHours: '24/7' },
  { symbol: 'SOL-USD', label: 'Solana', category: 'crypto', icon: '◎', description: 'Solana / US Dollar', tradingHours: '24/7' },
  { symbol: 'XRP-USD', label: 'XRP', category: 'crypto', icon: '✕', description: 'XRP / US Dollar', tradingHours: '24/7' },
  { symbol: 'ADA-USD', label: 'Cardano', category: 'crypto', icon: '₳', description: 'Cardano / US Dollar', tradingHours: '24/7' },
  { symbol: 'DOGE-USD', label: 'Dogecoin', category: 'crypto', icon: 'Ð', description: 'Dogecoin / US Dollar', tradingHours: '24/7' },

  // --- Stocks ---
  { symbol: 'AAPL', label: 'Apple', category: 'stock', icon: '🍎', description: 'Apple Inc.', tradingHours: 'NYSE' },
  { symbol: 'MSFT', label: 'Microsoft', category: 'stock', icon: '🪟', description: 'Microsoft Corp.', tradingHours: 'NASDAQ' },
  { symbol: 'GOOGL', label: 'Alphabet', category: 'stock', icon: '🔍', description: 'Alphabet Inc.', tradingHours: 'NASDAQ' },
  { symbol: 'AMZN', label: 'Amazon', category: 'stock', icon: '📦', description: 'Amazon.com Inc.', tradingHours: 'NASDAQ' },
  { symbol: 'NVDA', label: 'NVIDIA', category: 'stock', icon: '🖥️', description: 'NVIDIA Corp.', tradingHours: 'NASDAQ' },
  { symbol: 'TSLA', label: 'Tesla', category: 'stock', icon: '⚡', description: 'Tesla Inc.', tradingHours: 'NASDAQ' },
  { symbol: 'META', label: 'Meta', category: 'stock', icon: '👤', description: 'Meta Platforms Inc.', tradingHours: 'NASDAQ' },

  // --- Indices ---
  { symbol: '^GSPC', label: 'S&P 500', category: 'index', icon: '🏛️', description: 'S&P 500 Index', tradingHours: 'NYSE' },
  { symbol: '^IXIC', label: 'NASDAQ', category: 'index', icon: '💻', description: 'NASDAQ Composite', tradingHours: 'NASDAQ' },
  { symbol: '^DJI', label: 'Dow Jones', category: 'index', icon: '🏭', description: 'Dow Jones Industrial Average', tradingHours: 'NYSE' },

  // --- Commodities ---
  { symbol: 'GC=F', label: 'Gold', category: 'commodity', icon: '🥇', description: 'Gold Futures', tradingHours: 'COMEX' },
  { symbol: 'SI=F', label: 'Silver', category: 'commodity', icon: '🥈', description: 'Silver Futures', tradingHours: 'COMEX' },
  { symbol: 'CL=F', label: 'Crude Oil', category: 'commodity', icon: '🛢️', description: 'WTI Crude Oil Futures', tradingHours: 'NYMEX' },
];

export const MARKET_CATEGORIES = [
  { key: 'crypto', label: 'Crypto', color: '#FFB74D' },
  { key: 'stock', label: 'Stocks', color: '#00E676' },
  { key: 'index', label: 'Indices', color: '#1DE9B6' },
  { key: 'commodity', label: 'Commodities', color: '#00BFA5' },
] as const;

export const TIMEFRAMES = [
  { value: '1m', label: '1 Minute', shortLabel: '1m', description: 'Scalping — very short-term' },
  { value: '5m', label: '5 Minutes', shortLabel: '5m', description: 'Day trading — short-term' },
  { value: '15m', label: '15 Minutes', shortLabel: '15m', description: 'Intraday — short-term' },
  { value: '30m', label: '30 Minutes', shortLabel: '30m', description: 'Intraday — medium-term' },
  { value: '1h', label: '1 Hour', shortLabel: '1h', description: 'Swing trading — intraday' },
  { value: '4h', label: '4 Hours', shortLabel: '4h', description: 'Swing trading — multi-day' },
  { value: '1d', label: '1 Day', shortLabel: '1D', description: 'Position trading — daily' },
  { value: '1wk', label: '1 Week', shortLabel: '1W', description: 'Long-term — weekly' },
] as const;

export const getMarketBySymbol = (symbol: string): MarketDefinition | undefined =>
  MARKETS.find((m) => m.symbol === symbol);

export default MARKETS;
