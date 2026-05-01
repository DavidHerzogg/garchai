/**
 * GARCH AI — SafeArea Layout Component
 */
import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors } from '@/constants/Colors';

interface SafeAreaProps {
  children: React.ReactNode;
  style?: ViewStyle;
  edges?: ('top' | 'bottom' | 'left' | 'right')[];
}

export function SafeArea({ children, style, edges = ['top', 'bottom'] }: SafeAreaProps) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={[
        styles.container,
        edges.includes('top') && { paddingTop: insets.top },
        edges.includes('bottom') && { paddingBottom: insets.bottom },
        edges.includes('left') && { paddingLeft: insets.left },
        edges.includes('right') && { paddingRight: insets.right },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    // Default background — overridable via the `style` prop
    backgroundColor: Colors.background,
  },
});

export default SafeArea;
