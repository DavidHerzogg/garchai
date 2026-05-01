/**
 * GARCH AI — Select Component
 *
 * Custom dropdown/picker styled for dark theme. Uses a bottom sheet-style
 * modal on mobile for native-feeling selection.
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  FlatList,
  Pressable,
  ViewStyle,
} from 'react-native';
import Animated, { FadeIn, FadeOut, SlideInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

export interface SelectOption {
  value: string;
  label: string;
  icon?: string;
  description?: string;
}

interface SelectProps {
  label: string;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  error?: string;
  disabled?: boolean;
  containerStyle?: ViewStyle;
}

export function Select({
  label,
  options,
  value,
  onChange,
  placeholder = 'Select...',
  error,
  disabled = false,
  containerStyle,
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false);

  const selected = options.find((opt) => opt.value === value);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  return (
    <View style={[styles.container, containerStyle]}>
      <Text style={[styles.label, error && styles.labelError]}>{label}</Text>

      <TouchableOpacity
        style={[
          styles.trigger,
          isOpen && styles.triggerActive,
          error && styles.triggerError,
          disabled && styles.triggerDisabled,
        ]}
        onPress={() => !disabled && setIsOpen(true)}
        activeOpacity={0.8}
      >
        <View style={styles.triggerContent}>
          {selected?.icon && (
            <Text style={styles.triggerIcon}>{selected.icon}</Text>
          )}
          <Text
            style={[
              styles.triggerText,
              !selected && styles.placeholderText,
            ]}
          >
            {selected?.label || placeholder}
          </Text>
        </View>
        <Ionicons
          name={isOpen ? 'chevron-up' : 'chevron-down'}
          size={20}
          color={Colors.textTertiary}
        />
      </TouchableOpacity>

      {error && <Text style={styles.errorText}>{error}</Text>}

      <Modal
        visible={isOpen}
        transparent
        animationType="none"
        onRequestClose={() => setIsOpen(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setIsOpen(false)}>
          <Animated.View
            entering={FadeIn.duration(200)}
            exiting={FadeOut.duration(150)}
            style={styles.backdropInner}
          />
        </Pressable>

        <Animated.View
          entering={SlideInDown.duration(300).springify()}
          style={styles.sheet}
        >
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>{label}</Text>

          <FlatList
            data={options}
            keyExtractor={(item) => item.value}
            style={styles.optionsList}
            showsVerticalScrollIndicator={false}
            renderItem={({ item }) => {
              const isSelected = item.value === value;
              return (
                <TouchableOpacity
                  style={[
                    styles.option,
                    isSelected && styles.optionSelected,
                  ]}
                  onPress={() => handleSelect(item.value)}
                  activeOpacity={0.7}
                >
                  {item.icon && (
                    <Text style={styles.optionIcon}>{item.icon}</Text>
                  )}
                  <View style={styles.optionTextContainer}>
                    <Text
                      style={[
                        styles.optionLabel,
                        isSelected && styles.optionLabelSelected,
                      ]}
                    >
                      {item.label}
                    </Text>
                    {item.description && (
                      <Text style={styles.optionDescription}>
                        {item.description}
                      </Text>
                    )}
                  </View>
                  {isSelected && (
                    <Ionicons name="checkmark-circle" size={22} color={Colors.primary} />
                  )}
                </TouchableOpacity>
              );
            }}
          />
        </Animated.View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: Spacing.md,
  },
  label: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
    fontWeight: '500',
  },
  labelError: {
    color: Colors.danger,
  },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    minHeight: 52,
  },
  triggerActive: {
    borderColor: Colors.primary,
    borderWidth: 1.5,
  },
  triggerError: {
    borderColor: Colors.danger,
    backgroundColor: Colors.dangerMuted,
  },
  triggerDisabled: {
    opacity: 0.5,
  },
  triggerContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  triggerIcon: {
    fontSize: 20,
    marginRight: Spacing.sm,
  },
  triggerText: {
    ...Typography.body,
    color: Colors.textPrimary,
  },
  placeholderText: {
    color: Colors.textTertiary,
  },
  errorText: {
    ...Typography.caption,
    color: Colors.danger,
    marginTop: Spacing.xxs,
    marginLeft: Spacing.md,
  },

  // Bottom sheet
  backdrop: {
    flex: 1,
  },
  backdropInner: {
    flex: 1,
    backgroundColor: Colors.overlay,
  },
  sheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: Colors.surfaceElevated,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    maxHeight: '60%',
    paddingBottom: Spacing.xxl,
  },
  sheetHandle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.textDisabled,
    alignSelf: 'center',
    marginTop: Spacing.sm,
    marginBottom: Spacing.md,
  },
  sheetTitle: {
    ...Typography.h4,
    color: Colors.textPrimary,
    paddingHorizontal: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  optionsList: {
    paddingHorizontal: Spacing.md,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.xxs,
  },
  optionSelected: {
    backgroundColor: Colors.primaryMuted,
  },
  optionIcon: {
    fontSize: 22,
    marginRight: Spacing.sm,
  },
  optionTextContainer: {
    flex: 1,
  },
  optionLabel: {
    ...Typography.body,
    color: Colors.textPrimary,
  },
  optionLabelSelected: {
    color: Colors.primary,
    fontWeight: '600',
  },
  optionDescription: {
    ...Typography.caption,
    color: Colors.textTertiary,
    marginTop: 2,
  },
});

export default Select;
