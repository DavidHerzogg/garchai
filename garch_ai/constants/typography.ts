/**
 * GARCH AI Design System — Typography Tokens
 *
 * Uses Inter (Google Fonts) throughout for a clean, modern feel.
 * Provides ready-to-use text style objects for React Native StyleSheet.
 */
import { TextStyle, Platform } from 'react-native';

const fontFamily = Platform.select({
  ios: 'Inter',
  android: 'Inter',
  web: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
}) as string;

export const FontWeights = {
  regular: '400' as TextStyle['fontWeight'],
  medium: '500' as TextStyle['fontWeight'],
  semibold: '600' as TextStyle['fontWeight'],
  bold: '700' as TextStyle['fontWeight'],
};

export const FontSizes = {
  xs: 11,
  sm: 13,
  base: 15,
  md: 17,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
  display: 56,
};

export const LineHeights = {
  xs: 16,
  sm: 18,
  base: 22,
  md: 24,
  lg: 28,
  xl: 32,
  xxl: 40,
  xxxl: 48,
  display: 64,
};

/**
 * Pre-built text styles — use directly in StyleSheet or component style prop.
 *
 * Example: `<Text style={Typography.h1}>Dashboard</Text>`
 */
export const Typography: Record<string, TextStyle> = {
  // Display — hero sections, splash screens
  display: {
    fontFamily,
    fontSize: FontSizes.display,
    lineHeight: LineHeights.display,
    fontWeight: FontWeights.bold,
    letterSpacing: -1.5,
  },

  // Headings
  h1: {
    fontFamily,
    fontSize: FontSizes.xxxl,
    lineHeight: LineHeights.xxxl,
    fontWeight: FontWeights.bold,
    letterSpacing: -1,
  },
  h2: {
    fontFamily,
    fontSize: FontSizes.xxl,
    lineHeight: LineHeights.xxl,
    fontWeight: FontWeights.bold,
    letterSpacing: -0.5,
  },
  h3: {
    fontFamily,
    fontSize: FontSizes.xl,
    lineHeight: LineHeights.xl,
    fontWeight: FontWeights.semibold,
  },
  h4: {
    fontFamily,
    fontSize: FontSizes.lg,
    lineHeight: LineHeights.lg,
    fontWeight: FontWeights.semibold,
  },

  // Body text
  body: {
    fontFamily,
    fontSize: FontSizes.base,
    lineHeight: LineHeights.base,
    fontWeight: FontWeights.regular,
  },
  bodyMedium: {
    fontFamily,
    fontSize: FontSizes.base,
    lineHeight: LineHeights.base,
    fontWeight: FontWeights.medium,
  },
  bodySmall: {
    fontFamily,
    fontSize: FontSizes.sm,
    lineHeight: LineHeights.sm,
    fontWeight: FontWeights.regular,
  },

  // Labels and captions
  label: {
    fontFamily,
    fontSize: FontSizes.sm,
    lineHeight: LineHeights.sm,
    fontWeight: FontWeights.medium,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  caption: {
    fontFamily,
    fontSize: FontSizes.xs,
    lineHeight: LineHeights.xs,
    fontWeight: FontWeights.regular,
  },

  // Numbers / metrics display
  metric: {
    fontFamily,
    fontSize: FontSizes.xxl,
    lineHeight: LineHeights.xxl,
    fontWeight: FontWeights.bold,
    fontVariant: ['tabular-nums'],
  },
  metricSmall: {
    fontFamily,
    fontSize: FontSizes.lg,
    lineHeight: LineHeights.lg,
    fontWeight: FontWeights.semibold,
    fontVariant: ['tabular-nums'],
  },
  mono: {
    fontFamily: Platform.select({
      ios: 'Menlo',
      android: 'monospace',
      web: '"JetBrains Mono", "Fira Code", monospace',
    }),
    fontSize: FontSizes.sm,
    lineHeight: LineHeights.sm,
    fontWeight: FontWeights.regular,
  },

  // Buttons
  button: {
    fontFamily,
    fontSize: FontSizes.base,
    lineHeight: LineHeights.base,
    fontWeight: FontWeights.semibold,
    letterSpacing: 0.3,
  },
  buttonSmall: {
    fontFamily,
    fontSize: FontSizes.sm,
    lineHeight: LineHeights.sm,
    fontWeight: FontWeights.semibold,
    letterSpacing: 0.3,
  },
};

export default Typography;
