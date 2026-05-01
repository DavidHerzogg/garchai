/**
 * GARCH AI — LoadingSpinner Component
 *
 * Animated gradient spinner for loading states.
 */
import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing,
  FadeIn,
} from 'react-native-reanimated';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing } from '@/constants/spacing';

interface LoadingSpinnerProps {
  size?: number;
  message?: string;
  fullScreen?: boolean;
  style?: ViewStyle;
}

export function LoadingSpinner({
  size = 40,
  message,
  fullScreen = false,
  style,
}: LoadingSpinnerProps) {
  const rotation = useSharedValue(0);
  const pulse = useSharedValue(0.6);

  useEffect(() => {
    rotation.value = withRepeat(
      withTiming(360, { duration: 1000, easing: Easing.linear }),
      -1,
      false
    );
    pulse.value = withRepeat(
      withTiming(1, { duration: 800, easing: Easing.inOut(Easing.ease) }),
      -1,
      true
    );
  }, []);

  const spinStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  const pulseStyle = useAnimatedStyle(() => ({
    opacity: pulse.value,
  }));

  const spinner = (
    <Animated.View entering={FadeIn.duration(300)} style={[spinStyle, style]}>
      <View
        style={[
          styles.spinner,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            borderWidth: size > 30 ? 3 : 2,
          },
        ]}
      />
    </Animated.View>
  );

  if (fullScreen) {
    return (
      <View style={styles.fullScreen}>
        {spinner}
        {message && (
          <Animated.Text style={[styles.message, pulseStyle]}>
            {message}
          </Animated.Text>
        )}
      </View>
    );
  }

  return (
    <View style={[styles.inline, style]}>
      {spinner}
      {message && (
        <Animated.Text style={[styles.messageInline, pulseStyle]}>
          {message}
        </Animated.Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  spinner: {
    borderColor: Colors.border,
    borderTopColor: Colors.primary,
    borderRightColor: Colors.secondary,
  },
  fullScreen: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  inline: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.md,
  },
  message: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  messageInline: {
    ...Typography.caption,
    color: Colors.textTertiary,
    marginTop: Spacing.sm,
    textAlign: 'center',
  },
});

export default LoadingSpinner;
