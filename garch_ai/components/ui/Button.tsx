/**
 * GARCH AI — Button Component
 *
 * Premium button with gradient fills, press animations, and multiple variants.
 */
import React from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  style?: ViewStyle;
  fullWidth?: boolean;
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  icon,
  iconRight,
  style,
  fullWidth = false,
}: ButtonProps) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = () => {
    scale.value = withSpring(0.96, { damping: 15, stiffness: 300 });
  };

  const handlePressOut = () => {
    scale.value = withSpring(1, { damping: 15, stiffness: 300 });
  };

  const sizeStyles = SIZE_STYLES[size];
  const isDisabled = disabled || loading;

  const content = (
    <View style={[styles.content, sizeStyles.padding]}>
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === 'outline' || variant === 'ghost' ? Colors.primary : '#FFFFFF'}
        />
      ) : (
        <>
          {icon && <View style={styles.iconLeft}>{icon}</View>}
          <Text
            style={[
              sizeStyles.text,
              VARIANT_TEXT_STYLES[variant],
              isDisabled && styles.disabledText,
            ]}
          >
            {title}
          </Text>
          {iconRight && <View style={styles.iconRight}>{iconRight}</View>}
        </>
      )}
    </View>
  );

  if (variant === 'primary') {
    return (
      <AnimatedTouchable
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isDisabled}
        activeOpacity={0.9}
        style={[
          animatedStyle,
          fullWidth && styles.fullWidth,
          isDisabled && styles.disabledContainer,
          style,
        ]}
      >
        <LinearGradient
          colors={isDisabled ? ['#333', '#333'] : Colors.gradientPrimary as unknown as [string, string]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[styles.gradient, sizeStyles.borderRadius]}
        >
          {content}
        </LinearGradient>
      </AnimatedTouchable>
    );
  }

  return (
    <AnimatedTouchable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={isDisabled}
      activeOpacity={0.8}
      style={[
        animatedStyle,
        VARIANT_CONTAINER_STYLES[variant],
        sizeStyles.borderRadius,
        fullWidth && styles.fullWidth,
        isDisabled && styles.disabledContainer,
        style,
      ]}
    >
      {content}
    </AnimatedTouchable>
  );
}

const SIZE_STYLES = {
  sm: {
    padding: { paddingVertical: Spacing.xs, paddingHorizontal: Spacing.md } as ViewStyle,
    borderRadius: { borderRadius: BorderRadius.sm } as ViewStyle,
    text: { ...Typography.buttonSmall } as TextStyle,
  },
  md: {
    padding: { paddingVertical: Spacing.sm, paddingHorizontal: Spacing.lg } as ViewStyle,
    borderRadius: { borderRadius: BorderRadius.md } as ViewStyle,
    text: { ...Typography.button } as TextStyle,
  },
  lg: {
    padding: { paddingVertical: Spacing.md, paddingHorizontal: Spacing.xl } as ViewStyle,
    borderRadius: { borderRadius: BorderRadius.lg } as ViewStyle,
    text: { ...Typography.button, fontSize: 17 } as TextStyle,
  },
};

const VARIANT_CONTAINER_STYLES: Record<string, ViewStyle> = {
  secondary: {
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.borderLight,
  },
  outline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: Colors.primary,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  danger: {
    backgroundColor: Colors.danger,
  },
};

const VARIANT_TEXT_STYLES: Record<string, TextStyle> = {
  primary: { color: '#FFFFFF' },
  secondary: { color: Colors.textPrimary },
  outline: { color: Colors.primary },
  ghost: { color: Colors.primary },
  danger: { color: '#FFFFFF' },
};

const styles = StyleSheet.create({
  gradient: {
    overflow: 'hidden',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconLeft: {
    marginRight: Spacing.xs,
  },
  iconRight: {
    marginLeft: Spacing.xs,
  },
  fullWidth: {
    width: '100%',
  },
  disabledContainer: {
    opacity: 0.5,
  },
  disabledText: {
    opacity: 0.7,
  },
});

export default Button;
