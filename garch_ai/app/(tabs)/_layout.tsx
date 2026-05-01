/**
 * GARCH AI — Tab Navigation Layout
 *
 * SafeArea fix:
 *   - Tab bar height is fully driven by useSafeAreaInsets().bottom
 *   - No hardcoded Platform.OS === 'ios' ? 88 : 64 magic numbers
 *   - This ensures the bar never overlaps the home indicator on iPhone
 *     or the navigation bar on Android gesture-nav devices
 */
import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';

import { useUser } from '@clerk/expo';
import { useMutation } from 'convex/react';
import { api } from '@/convex/_generated/api';

// Tappable height above the safe area inset — slightly increased for better prominence
const TAB_CONTENT_HEIGHT = 62;

export default function TabLayout() {
  const { user } = useUser();
  const syncUser = useMutation(api.users.sync);
  const insets = useSafeAreaInsets();

  // Sync user to Convex on mount / login
  React.useEffect(() => {
    if (user) {
      syncUser({
        clerkId: user.id,
        email: user.primaryEmailAddress?.emailAddress ?? '',
        name: user.fullName ?? undefined,
        imageUrl: user.imageUrl ?? undefined,
      }).catch((err) => {
        console.error('Failed to sync user to Convex:', err);
      });
    }
  }, [user, syncUser]);

  // Total bar height = visible icon+label area + device bottom inset
  const tabBarHeight = TAB_CONTENT_HEIGHT + insets.bottom;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          // Height fully derived from insets — no hardcoded values
          height: tabBarHeight,
          // Slightly more padding to push icons up for better ergonomics
          paddingBottom: insets.bottom + 4,
          paddingTop: 10,
        },
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textTertiary,
        tabBarLabelStyle: styles.tabLabel,
        tabBarItemStyle: styles.tabItem,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Strategy',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'stats-chart' : 'stats-chart-outline'} size={24} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'settings' : 'settings-outline'} size={24} color={color} />
          ),
        }}
      />

    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabLabel: {
    fontSize: 11,
    fontWeight: '500',
    marginTop: 2,
  },
  tabItem: {
    paddingTop: 4,
  },
});
