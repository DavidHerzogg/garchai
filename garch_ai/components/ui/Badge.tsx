/**
 * GARCH AI — Badge Component
 *
 * Small status labels with semantic coloring.
 */
import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

export type BadgeVariant = 'default' | 'success' | 'danger' | 'warning' | 'info' | 'primary';

interface BadgeProps {
  text: string;
  variant?: BadgeVariant;
  size?: 'sm' | 'md';
  style?: ViewStyle;
  dot?: boolean;
}

export function Badge({
  text,
  variant = 'default',
  size = 'md',
  style,
  dot = false,
}: BadgeProps) {
  const variantColors = VARIANT_MAP[variant];

  return (
    <View
      style={[
        styles.container,
        size === 'sm' && styles.containerSm,
        { backgroundColor: variantColors.bg, borderColor: variantColors.border },
        style,
      ]}
    >
      {dot && (
        <View style={[styles.dot, { backgroundColor: variantColors.text }]} />
      )}
      <Text
        style={[
          size === 'sm' ? styles.textSm : styles.text,
          { color: variantColors.text },
        ]}
      >
        {text}
      </Text>
    </View>
  );
}

const VARIANT_MAP: Record<BadgeVariant, { bg: string; text: string; border: string }> = {
  default: {
    bg: Colors.surfaceElevated,
    text: Colors.textSecondary,
    border: Colors.border,
  },
  success: {
    bg: Colors.successMuted,
    text: Colors.success,
    border: 'rgba(0, 230, 118, 0.25)',
  },
  danger: {
    bg: Colors.dangerMuted,
    text: Colors.danger,
    border: 'rgba(255, 82, 82, 0.25)',
  },
  warning: {
    bg: Colors.warningMuted,
    text: Colors.warning,
    border: 'rgba(255, 183, 77, 0.25)',
  },
  info: {
    bg: Colors.infoMuted,
    text: Colors.info,
    border: 'rgba(66, 165, 245, 0.25)',
  },
  primary: {
    bg: Colors.primaryMuted,
    text: Colors.primary,
    border: 'rgba(108, 99, 255, 0.25)',
  },
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xxs + 1,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
  },
  containerSm: {
    paddingHorizontal: Spacing.xs,
    paddingVertical: 2,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: Spacing.xxs,
  },
  text: {
    ...Typography.caption,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  textSm: {
    fontSize: 10,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
});

export default Badge;
