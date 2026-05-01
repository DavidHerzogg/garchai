/**
 * GARCH AI — Card Component
 *
 * Glassmorphism card with subtle gradient border and elevation options.
 */
import React from 'react';
import {
  View,
  StyleSheet,
  ViewStyle,
  TouchableOpacity,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';
import { Colors } from '@/constants/Colors';
import { Spacing, BorderRadius } from '@/constants/spacing';

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

export type CardVariant = 'default' | 'elevated' | 'gradient' | 'outlined';

interface CardProps {
  children: React.ReactNode;
  variant?: CardVariant;
  onPress?: () => void;
  style?: ViewStyle;
  animateEntry?: boolean;
  entryDelay?: number;
  noPadding?: boolean;
}

export function Card({
  children,
  variant = 'default',
  onPress,
  style,
  animateEntry = false,
  entryDelay = 0,
  noPadding = false,
}: CardProps) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = () => {
    if (onPress) {
      scale.value = withSpring(0.98, { damping: 15, stiffness: 300 });
    }
  };

  const handlePressOut = () => {
    if (onPress) {
      scale.value = withSpring(1, { damping: 15, stiffness: 300 });
    }
  };

  const containerStyle: ViewStyle[] = [
    styles.base,
    !noPadding && styles.padding,
    VARIANT_STYLES[variant],
    style as ViewStyle,
  ].filter(Boolean) as ViewStyle[];

  const entering = animateEntry
    ? FadeInDown.delay(entryDelay).duration(400).springify()
    : undefined;

  if (variant === 'gradient') {
    const Wrapper = onPress ? AnimatedTouchable : Animated.View;
    const wrapperProps = onPress
      ? {
          onPress,
          onPressIn: handlePressIn,
          onPressOut: handlePressOut,
          activeOpacity: 0.95,
        }
      : {};

    return (
      <Wrapper
        entering={entering}
        style={[animatedStyle, style]}
        {...wrapperProps}
      >
        <LinearGradient
          colors={Colors.gradientCard as unknown as [string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[styles.base, !noPadding && styles.padding, styles.gradientInner]}
        >
          <View style={styles.gradientBorder} />
          {children}
        </LinearGradient>
      </Wrapper>
    );
  }

  if (onPress) {
    return (
      <AnimatedTouchable
        entering={entering}
        style={[animatedStyle, ...containerStyle]}
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        activeOpacity={0.95}
      >
        {children}
      </AnimatedTouchable>
    );
  }

  return (
    <Animated.View entering={entering} style={containerStyle}>
      {children}
    </Animated.View>
  );
}

const VARIANT_STYLES: Record<CardVariant, ViewStyle> = {
  default: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  elevated: {
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.borderLight,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.3,
    shadowRadius: 16,
    elevation: 8,
  },
  gradient: {},
  outlined: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: Colors.borderLight,
  },
};

const styles = StyleSheet.create({
  base: {
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
  },
  padding: {
    padding: Spacing.md,
  },
  gradientInner: {
    borderWidth: 1,
    borderColor: Colors.glassStroke,
  },
  gradientBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
  },
});

export default Card;
