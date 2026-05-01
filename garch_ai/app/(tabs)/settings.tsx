/**
 * GARCH AI — Settings Screen
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Switch, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useRouter } from 'expo-router';
import { useClerk, useUser } from '@clerk/expo';
import { SafeArea } from '@/components/layout/SafeArea';
import { Header } from '@/components/layout/Header';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing, BorderRadius } from '@/constants/spacing';

export default function SettingsScreen() {
  const { signOut } = useClerk();
  const { user } = useUser();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await signOut();
      router.replace('/(auth)/sign-in');
    } catch (err: any) {
      console.error('Sign out error:', err);
      setSigningOut(false);
    }
  };

  return (
    <SafeArea edges={['top']}>
      <Header title="Settings" />

      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Subscription Card */}
        <Animated.View entering={FadeInDown.delay(100).duration(400)}>
          <Card variant="gradient" style={styles.subCard}>
            <View style={styles.subHeader}>
              <View>
                <Text style={styles.subTitle}>Free Plan</Text>
                <Text style={styles.subSubtitle}>3 backtests per day</Text>
              </View>
              <Badge text="Current" variant="primary" />
            </View>
            <View style={styles.usageBar}>
              <View style={[styles.usageFill, { width: '0%' }]} />
            </View>
            <Text style={styles.usageText}>0 / 3 backtests used today</Text>
            <TouchableOpacity style={styles.upgradeButton}>
              <Text style={styles.upgradeText}>Upgrade to Pro</Text>
              <Ionicons name="arrow-forward" size={16} color={Colors.primary} />
            </TouchableOpacity>
          </Card>
        </Animated.View>

        {/* Account Section */}
        <Animated.View entering={FadeInDown.delay(200).duration(400)}>
          <Text style={styles.sectionTitle}>Account</Text>
          <Card variant="default" noPadding>
            <SettingsRow icon="person-outline" label="Profile" value={user?.fullName || 'Not signed in'} />
            <SettingsRow icon="mail-outline" label="Email" value={user?.primaryEmailAddress?.emailAddress || '—'} />
            <SettingsRow icon="card-outline" label="Subscription" value="Free" last />
          </Card>
        </Animated.View>

        {/* Preferences */}
        <Animated.View entering={FadeInDown.delay(300).duration(400)}>
          <Text style={styles.sectionTitle}>Preferences</Text>
          <Card variant="default" noPadding>
            <SettingsRow icon="moon-outline" label="Dark Mode" toggle defaultValue={true} />
            <SettingsRow icon="notifications-outline" label="Notifications" toggle defaultValue={false} />
            <SettingsRow icon="analytics-outline" label="Default Timeframe" value="1D" last />
          </Card>
        </Animated.View>

        {/* About */}
        <Animated.View entering={FadeInDown.delay(400).duration(400)}>
          <Text style={styles.sectionTitle}>About</Text>
          <Card variant="default" noPadding>
            <SettingsRow icon="information-circle-outline" label="Version" value="1.0.0" />
            <SettingsRow icon="document-text-outline" label="Terms of Service" chevron />
            <SettingsRow icon="shield-checkmark-outline" label="Privacy Policy" chevron last />
          </Card>
        </Animated.View>

        {/* Sign Out */}
        <Animated.View entering={FadeInDown.delay(500).duration(400)}>
          <TouchableOpacity
            style={[styles.signOutButton, signingOut && styles.signOutDisabled]}
            onPress={handleSignOut}
            disabled={signingOut}
            activeOpacity={0.75}
          >
            {signingOut ? (
              <ActivityIndicator size="small" color={Colors.danger} />
            ) : (
              <Ionicons name="log-out-outline" size={20} color={Colors.danger} />
            )}
            <Text style={styles.signOutText}>
              {signingOut ? 'Signing out…' : 'Sign Out'}
            </Text>
          </TouchableOpacity>
        </Animated.View>
      </ScrollView>
    </SafeArea>
  );
}

function SettingsRow({
  icon,
  label,
  value,
  toggle,
  defaultValue,
  chevron,
  last,
}: {
  icon: string;
  label: string;
  value?: string;
  toggle?: boolean;
  defaultValue?: boolean;
  chevron?: boolean;
  last?: boolean;
}) {
  return (
    <View style={[styles.row, !last && styles.rowBorder]}>
      <View style={styles.rowLeft}>
        <Ionicons name={icon as any} size={20} color={Colors.textSecondary} />
        <Text style={styles.rowLabel}>{label}</Text>
      </View>
      {toggle ? (
        <Switch
          value={defaultValue}
          trackColor={{ false: Colors.surfaceElevated, true: Colors.primaryDark }}
          thumbColor={defaultValue ? Colors.primary : Colors.textDisabled}
        />
      ) : chevron ? (
        <Ionicons name="chevron-forward" size={18} color={Colors.textDisabled} />
      ) : (
        <Text style={styles.rowValue}>{value}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.xxl },
  subCard: { marginBottom: Spacing.lg },
  subHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: Spacing.md },
  subTitle: { ...Typography.h4, color: Colors.textPrimary },
  subSubtitle: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },
  usageBar: {
    height: 6, backgroundColor: Colors.surface, borderRadius: 3,
    marginBottom: Spacing.xs, overflow: 'hidden',
  },
  usageFill: { height: '100%', backgroundColor: Colors.primary, borderRadius: 3 },
  usageText: { ...Typography.caption, color: Colors.textTertiary, marginBottom: Spacing.md },
  upgradeButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: Colors.primaryMuted, borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm, gap: Spacing.xs,
  },
  upgradeText: { ...Typography.button, color: Colors.primary },
  sectionTitle: {
    ...Typography.label, color: Colors.textTertiary,
    marginBottom: Spacing.sm, marginTop: Spacing.md,
  },
  row: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md, minHeight: 52,
  },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: Colors.border },
  rowLeft: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  rowLabel: { ...Typography.body, color: Colors.textPrimary },
  rowValue: { ...Typography.bodySmall, color: Colors.textSecondary },
  signOutButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.xs, paddingVertical: Spacing.md, marginTop: Spacing.lg,
    borderRadius: BorderRadius.md,
  },
  signOutDisabled: { opacity: 0.55 },
  signOutText: { ...Typography.button, color: Colors.danger },
});
