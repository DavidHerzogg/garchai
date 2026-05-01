/**
 * GARCH AI — Equity Curve Chart
 * Renders backtest equity curve as a smooth line chart.
 * Uses react-native-gifted-charts (already installed).
 *
 * Props:
 *   data        — array of { timestamp, equity, drawdown_pct }
 *   height      — chart height in px (default 220)
 *   showDrawdown— render drawdown overlay (default false)
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

export interface EquityPoint {
  timestamp:   string;
  equity:      number;
  drawdownPct: number;
}

interface Props {
  data:          EquityPoint[];
  initialCapital?: number;
  height?:       number;
  showDrawdown?: boolean;
}

const SCREEN_W = Dimensions.get('window').width;

export function EquityCurveChart({
  data,
  initialCapital = 10_000,
  height = 220,
  showDrawdown = false,
}: Props) {
  const { equityPoints, drawdownPoints, returnPct, isPositive } = useMemo(() => {
    if (!data?.length) return { equityPoints: [], drawdownPoints: [], returnPct: 0, isPositive: true };

    // Downsample to max 300 points for performance
    const step   = Math.max(1, Math.floor(data.length / 300));
    const sample = data.filter((_, i) => i % step === 0 || i === data.length - 1);

    const equityPoints = sample.map(p => ({ value: parseFloat(p.equity.toFixed(2)) }));
    const drawdownPoints = sample.map(p => ({ value: parseFloat(Math.abs(p.drawdownPct).toFixed(2)) }));

    const first = data[0].equity;
    const last  = data[data.length - 1].equity;
    const returnPct = ((last - first) / first) * 100;

    return { equityPoints, drawdownPoints, returnPct, isPositive: returnPct >= 0 };
  }, [data]);

  if (!equityPoints.length) {
    return (
      <View style={[styles.empty, { height }]}>
        <Text style={styles.emptyText}>No equity data</Text>
      </View>
    );
  }

  const lineColor = isPositive ? Colors.success : Colors.danger;
  const chartWidth = SCREEN_W - Spacing.lg * 2 - 32; // account for padding

  return (
    <View style={styles.wrapper}>
      {/* Legend row */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: lineColor }]} />
          <Text style={styles.legendLabel}>Equity</Text>
        </View>
        {showDrawdown && (
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: Colors.danger }]} />
            <Text style={styles.legendLabel}>Drawdown</Text>
          </View>
        )}
        <Text style={[styles.returnLabel, { color: lineColor }]}>
          {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
        </Text>
      </View>

      {/* Main equity line */}
      <LineChart
        data={equityPoints}
        width={chartWidth}
        height={height}
        color={lineColor}
        thickness={2}
        startFillColor={lineColor}
        endFillColor={Colors.background}
        startOpacity={0.18}
        endOpacity={0.01}
        areaChart
        curved
        hideDataPoints
        hideYAxisText={false}
        yAxisTextStyle={styles.axisText}
        xAxisLabelTextStyle={styles.axisText}
        noOfSections={4}
        xAxisColor="transparent"
        yAxisColor="transparent"
        rulesColor={Colors.chartGrid}
        rulesType="solid"
        backgroundColor={Colors.surface}
        isAnimated
        animationDuration={800}
        hideOrigin
        initialSpacing={0}
        spacing={chartWidth / Math.max(equityPoints.length - 1, 1)}
      />

      {/* Drawdown overlay */}
      {showDrawdown && drawdownPoints.length > 0 && (
        <View style={styles.drawdownContainer}>
          <Text style={styles.drawdownLabel}>Drawdown (%)</Text>
          <LineChart
            data={drawdownPoints}
            width={chartWidth}
            height={80}
            color={Colors.danger}
            thickness={1.5}
            startFillColor={Colors.danger}
            endFillColor={Colors.background}
            startOpacity={0.15}
            endOpacity={0.01}
            areaChart
            curved
            hideDataPoints
            yAxisTextStyle={styles.axisText}
            noOfSections={2}
            xAxisColor="transparent"
            yAxisColor="transparent"
            rulesColor={Colors.chartGrid}
            backgroundColor={Colors.surface}
            isAnimated
            animationDuration={600}
            initialSpacing={0}
            spacing={chartWidth / Math.max(drawdownPoints.length - 1, 1)}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    overflow: 'hidden',
  },
  legend: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.sm,
    gap: Spacing.sm,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot:  { width: 8, height: 8, borderRadius: 4 },
  legendLabel:{ ...Typography.caption, color: Colors.textTertiary },
  returnLabel:{ ...Typography.bodyMedium, fontWeight: '700', marginLeft: 'auto' } as any,
  axisText:   { ...Typography.caption, color: Colors.textDisabled, fontSize: 10 } as any,
  empty: {
    justifyContent: 'center', alignItems: 'center',
    backgroundColor: Colors.surface, borderRadius: BorderRadius.lg,
  },
  emptyText: { ...Typography.caption, color: Colors.textDisabled },
  drawdownContainer: { marginTop: Spacing.sm },
  drawdownLabel:     { ...Typography.caption, color: Colors.danger, marginBottom: 4 },
});

export default EquityCurveChart;
