/**
 * GARCH AI Design System — Color Tokens
 *
 * Premium dark theme inspired by trading terminals and fintech apps.
 * Glassmorphism-ready with carefully calibrated opacity values.
 */

export const Colors = {
  // Core backgrounds — near-black with subtle blue undertone
  background: '#0A0A0F',
  backgroundSecondary: '#0E0E16',
  surface: '#12121A',
  surfaceElevated: '#1A1A2E',
  surfaceHover: '#22223A',

  // Accent palette
  primary: '#00E676',       // Vivid Green — main accent
  primaryLight: '#66FFA6',
  primaryDark: '#00B448',
  primaryMuted: 'rgba(0, 230, 118, 0.15)',

  secondary: '#1DE9B6',     // Teal — secondary accent
  secondaryLight: '#64FFDA',
  secondaryDark: '#00BFA5',
  secondaryMuted: 'rgba(29, 233, 182, 0.15)',

  // Semantic
  success: '#00E676',
  successLight: '#33EB91',
  successDark: '#00B85C',
  successMuted: 'rgba(0, 230, 118, 0.15)',

  danger: '#FF5252',
  dangerLight: '#FF7474',
  dangerDark: '#E53535',
  dangerMuted: 'rgba(255, 82, 82, 0.15)',

  warning: '#FFB74D',
  warningLight: '#FFC570',
  warningDark: '#F5A623',
  warningMuted: 'rgba(255, 183, 77, 0.15)',

  info: '#42A5F5',
  infoMuted: 'rgba(66, 165, 245, 0.15)',

  // Text hierarchy
  textPrimary: '#FFFFFF',
  textSecondary: '#A0A0B0',
  textTertiary: '#6B6B80',
  textDisabled: '#444455',

  // Borders & dividers
  border: 'rgba(255, 255, 255, 0.06)',
  borderLight: 'rgba(255, 255, 255, 0.12)',
  borderAccent: 'rgba(0, 230, 118, 0.3)',

  // Glass / overlay
  glassBg: 'rgba(18, 18, 26, 0.75)',
  glassStroke: 'rgba(255, 255, 255, 0.08)',
  overlay: 'rgba(0, 0, 0, 0.6)',

  // Gradients (as arrays for LinearGradient)
  gradientPrimary: ['#00E676', '#1DE9B6'],
  gradientDark: ['#0A0A0F', '#12121A'],
  gradientCard: ['rgba(0, 230, 118, 0.08)', 'rgba(29, 233, 182, 0.04)'],
  gradientSuccess: ['#00E676', '#1DE9B6'],
  gradientDanger: ['#FF5252', '#FF7474'],

  // Chart-specific
  chartLine: '#00E676',
  chartFill: 'rgba(0, 230, 118, 0.2)',
  chartGrid: 'rgba(255, 255, 255, 0.04)',
  chartBuy: '#00E676',
  chartSell: '#FF5252',
  chartBenchmark: '#FFB74D',
} as const;

export type ColorKey = keyof typeof Colors;
export default Colors;
