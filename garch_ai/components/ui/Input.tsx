/**
 * GARCH AI — Input Component
 *
 * Fixed: floating label no longer overlaps placeholder.
 * Pattern: label sits above the field (static) when focused/filled,
 * and acts as placeholder when the field is empty and unfocused.
 * The native TextInput placeholder is only shown when focused,
 * preventing the label+placeholder double-render.
 */
import React, { useState, useRef } from 'react';
import {
  View,
  TextInput,
  Text,
  StyleSheet,
  ViewStyle,
  TextInputProps,
  TouchableWithoutFeedback,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
  interpolate,
  interpolateColor,
} from 'react-native-reanimated';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

interface InputProps extends Omit<TextInputProps, 'style'> {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  error?: string;
  helper?: string;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  containerStyle?: ViewStyle;
  disabled?: boolean;
}

export function Input({
  label,
  value,
  onChangeText,
  error,
  helper,
  icon,
  iconRight,
  containerStyle,
  disabled = false,
  placeholder,
  ...textInputProps
}: InputProps) {
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<TextInput>(null);

  // Label floats up when the field has content OR is focused
  const isFloating = isFocused || value.length > 0;
  const focusAnim = useSharedValue(isFloating ? 1 : 0);

  React.useEffect(() => {
    focusAnim.value = withTiming(isFloating ? 1 : 0, { duration: 180 });
  }, [isFloating]);

  const labelAnimStyle = useAnimatedStyle(() => ({
    transform: [
      // Translate upward to sit above the text field
      { translateY: interpolate(focusAnim.value, [0, 1], [0, -22]) },
      { scale: interpolate(focusAnim.value, [0, 1], [1, 0.82]) },
    ],
    color: interpolateColor(
      focusAnim.value,
      [0, 1],
      [
        Colors.textTertiary,
        error ? Colors.danger : isFocused ? Colors.primary : Colors.textSecondary,
      ]
    ),
  }));

  const borderColor = error
    ? Colors.danger
    : isFocused
    ? Colors.primary
    : Colors.border;

  return (
    <TouchableWithoutFeedback onPress={() => inputRef.current?.focus()}>
      <View style={[styles.container, containerStyle]}>
        <View
          style={[
            styles.inputContainer,
            { borderColor },
            isFocused && styles.inputFocused,
            error && styles.inputError,
            disabled && styles.inputDisabled,
          ]}
        >
          {icon && <View style={styles.iconLeft}>{icon}</View>}

          {/* Label + input stacked vertically inside the field */}
          <View style={styles.inputWrapper}>
            {/* Floating label — acts as placeholder when not floated */}
            <Animated.Text
              style={[styles.label, labelAnimStyle]}
              numberOfLines={1}
              pointerEvents="none"
            >
              {label}
            </Animated.Text>

            {/* The actual TextInput — positioned below the floated label */}
            <TextInput
              ref={inputRef}
              value={value}
              onChangeText={onChangeText}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              style={[styles.input, disabled && styles.textDisabled]}
              // Only show the native placeholder when focused (label has floated up)
              placeholder={isFocused ? placeholder : undefined}
              placeholderTextColor={Colors.textDisabled}
              selectionColor={Colors.primary}
              editable={!disabled}
              {...textInputProps}
            />
          </View>

          {iconRight && <View style={styles.iconRight}>{iconRight}</View>}
        </View>

        {(error || helper) && (
          <Text style={[styles.helperText, error && styles.errorText]}>
            {error || helper}
          </Text>
        )}
      </View>
    </TouchableWithoutFeedback>
  );
}

const FIELD_HEIGHT = 60;
// Label starts centred in the field; translateY moves it to the top area
const LABEL_TOP = (FIELD_HEIGHT - 20) / 2; // ≈ 20 — visually centred when not floated

const styles = StyleSheet.create({
  container: {
    marginBottom: Spacing.md,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    height: FIELD_HEIGHT,
    overflow: 'hidden',
  },
  inputFocused: {
    borderWidth: 1.5,
    backgroundColor: Colors.backgroundSecondary,
  },
  inputError: {
    backgroundColor: Colors.dangerMuted,
  },
  inputDisabled: {
    opacity: 0.5,
  },
  inputWrapper: {
    flex: 1,
    height: FIELD_HEIGHT,
    justifyContent: 'center',
  },
  label: {
    position: 'absolute',
    left: 0,
    // Centred vertically in the field when not floated
    top: LABEL_TOP,
    ...Typography.body,
    color: Colors.textTertiary,
    // Fix scaling origin so it shrinks toward the left
    transformOrigin: 'left center',
  },
  input: {
    // Push the text input down so it sits below the floated label
    marginTop: 14,
    ...Typography.body,
    color: Colors.textPrimary,
    padding: 0,
    // Ensure the cursor and text are vertically centred within their slot
    height: 28,
    textAlignVertical: 'center',
  },
  iconLeft: {
    marginRight: Spacing.sm,
  },
  iconRight: {
    marginLeft: Spacing.sm,
  },
  helperText: {
    ...Typography.caption,
    color: Colors.textTertiary,
    marginTop: Spacing.xxs,
    marginLeft: Spacing.md,
  },
  errorText: {
    color: Colors.danger,
  },
  textDisabled: {
    color: Colors.textDisabled,
  },
});

export default Input;
