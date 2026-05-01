/**
 * GARCH AI — Sign In Screen
 *
 * Layout:
 *   1. Logo — simple arc emoji on dark-green rounded square
 *   2. Illustration (SVG, larger)
 *   3a. Default state:  [ Continue with Google ] + [ Continue with Email ]
 *   3b. Email state:    BOTH buttons hidden → email form + back link
 *
 * Background: dark gray (#1C1C1E) instead of near-black
 */
import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TouchableOpacity,
  Image,
  ActivityIndicator,
} from 'react-native';
import { useRouter, Link } from 'expo-router';
import { useSignIn, useSSO, useClerk } from '@clerk/expo';
import * as Linking from 'expo-linking';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown, FadeInUp, FadeIn } from 'react-native-reanimated';
import { SafeArea } from '@/components/layout/SafeArea';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import IllustrationSvg from '@/components/ui/IllustrationSvg';
import { Colors } from '@/constants/Colors';
import { Typography } from '@/constants/typography';
import { Spacing } from '@/constants/spacing';

// No custom bg — use SafeArea default (Colors.background = #0A0A0F)

export default function SignInScreen() {
  const { signIn } = useSignIn();
  const { setActive } = useClerk();
  const { startSSOFlow } = useSSO();
  const router = useRouter();

  // Progressive disclosure
  const [showEmailForm, setShowEmailForm] = useState(false);

  // Email form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);
  const [error, setError] = useState('');

  // Google SSO guard
  const [googleLoading, setGoogleLoading] = useState(false);

  // ── Email sign-in (Clerk v3 Signals/Future API) ────────────────────────────
  const onSignInPress = async () => {
    if (!signIn) return;
    setEmailLoading(true);
    setError('');

    try {
      const { error: createError } = await signIn.create({ identifier: email });
      if (createError) {
        setError(createError.longMessage || createError.message || 'Invalid email or password.');
        return;
      }

      const { error: passwordError } = await signIn.password({ password });
      if (passwordError) {
        setError(passwordError.longMessage || passwordError.message || 'Invalid email or password.');
        return;
      }

      if (signIn.status === 'complete') {
        await setActive({ session: signIn.createdSessionId });
        router.replace('/(tabs)');
      } else {
        setError('Additional verification required. Please try again.');
      }
    } catch (err: any) {
      setError(
        err?.errors?.[0]?.longMessage ||
        err?.errors?.[0]?.message ||
        'Invalid email or password.'
      );
    } finally {
      setEmailLoading(false);
    }
  };

  // ── Google SSO ─────────────────────────────────────────────────────────────
  const onGoogleSignInPress = useCallback(async () => {
    if (googleLoading) return;
    setGoogleLoading(true);
    setError('');

    try {
      const redirectUrl = Linking.createURL('/');
      const result = await startSSOFlow({ strategy: 'oauth_google', redirectUrl });
      if (result?.createdSessionId) {
        await setActive({ session: result.createdSessionId });
        router.replace('/(tabs)');
      }
    } catch (err: any) {
      setError(
        err?.errors?.[0]?.longMessage ||
        err?.message ||
        'Google Sign-In failed. Please try again.'
      );
    } finally {
      setGoogleLoading(false);
    }
  }, [googleLoading, startSSOFlow]);

  return (
    <SafeArea>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.container}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* ── Logo — matches sign-up style ──────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(0).duration(450)} style={styles.logoRow}>
            <View style={styles.logoContainer}>
              <Image
                source={require('@/assets/images/Garch_Ai_APP_Logo_Background.png')}
                style={styles.logo}
                resizeMode="contain"
              />
            </View>
            <Text style={styles.welcomeTitle}>Welcome Back</Text>
            <Text style={styles.welcomeSubtitle}>Sign in to continue your trading journey</Text>
          </Animated.View>

          {/* ── Illustration ─────────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(80).duration(550)} style={styles.illustrationWrapper}>
            <IllustrationSvg width="100%" height={300} />
          </Animated.View>

          {/* ── Error banner ─────────────────────────────────────────────── */}
          {error ? (
            <Animated.View entering={FadeIn.duration(250)} style={styles.errorBanner}>
              <Ionicons name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.errorText}>{error}</Text>
            </Animated.View>
          ) : null}

          {/* ── CTA / Email form ─────────────────────────────────────────── */}
          <Animated.View entering={FadeInUp.delay(160).duration(450)} style={styles.ctaSection}>
            {!showEmailForm ? (
              /* Default: show both buttons */
              <>
                <TouchableOpacity
                  style={[styles.googleBtn, googleLoading && styles.btnDisabled]}
                  onPress={onGoogleSignInPress}
                  disabled={googleLoading}
                  activeOpacity={0.87}
                >
                  {googleLoading
                    ? <ActivityIndicator size="small" color={Colors.background} />
                    : <Ionicons name="logo-google" size={20} color={Colors.background} />
                  }
                  <Text style={styles.googleBtnText}>
                    {googleLoading ? 'Connecting…' : 'Continue with Google'}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.emailBtn}
                  onPress={() => { setShowEmailForm(true); setError(''); }}
                  activeOpacity={0.78}
                >
                  <Ionicons name="mail-outline" size={20} color={Colors.textPrimary} />
                  <Text style={styles.emailBtnText}>Continue with Email</Text>
                </TouchableOpacity>
              </>
            ) : (
              /* Email form: both buttons are gone */
              <Animated.View entering={FadeInDown.duration(320)} style={styles.emailForm}>
                <Input
                  label="Email Address"
                  placeholder="name@example.com"
                  value={email}
                  onChangeText={setEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoComplete="email"
                />
                <Input
                  label="Password"
                  placeholder="••••••••"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  autoComplete="password"
                />
                <Button
                  title="Sign In"
                  onPress={onSignInPress}
                  loading={emailLoading}
                  disabled={!email || !password || !signIn}
                  fullWidth
                  size="lg"
                />
                {/* Back link — tapping reveals the original buttons again */}
                <TouchableOpacity
                  style={styles.backLink}
                  onPress={() => { setShowEmailForm(false); setError(''); }}
                >
                  <Ionicons name="arrow-back" size={15} color={Colors.textSecondary} />
                  <Text style={styles.backLinkText}>Other sign-in options</Text>
                </TouchableOpacity>
              </Animated.View>
            )}

            {/* Footer */}
            <View style={styles.footer}>
              <Text style={styles.footerText}>Don't have an account? </Text>
              <Link href="/(auth)/sign-up" asChild>
                <TouchableOpacity>
                  <Text style={styles.footerLink}>Sign Up</Text>
                </TouchableOpacity>
              </Link>
            </View>
          </Animated.View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeArea>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.xl,
  },

  // ── Logo — sign-up style ─────────────────────────────────────────────
  logoRow: {
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  logoContainer: {
    width: 100,
    height: 100,
    backgroundColor: 'rgba(0, 230, 118, 0.06)',
    borderRadius: 26,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(0, 230, 118, 0.12)',
  },
  logo: {
    width: 76,
    height: 76,
    // Nudge down so the image is visually centred in the rounded container
    marginTop: 4,
  },
  welcomeTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  welcomeSubtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.xxs,
    textAlign: 'center',
  },

  // ── Illustration ────────────────────────────────────────────────────────
  illustrationWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    // Fill all available vertical space between logo and CTA buttons
    flex: 1,
    minHeight: 240,
    marginVertical: Spacing.lg,
  },

  // ── CTA section ─────────────────────────────────────────────────────────
  ctaSection: {
    width: '100%',
    gap: Spacing.md,
  },

  // Google button — primary green
  googleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.primary,
    borderRadius: 16,
    paddingVertical: 17,
    paddingHorizontal: Spacing.xl,
    gap: 10,
  },
  btnDisabled: { opacity: 0.6 },
  googleBtnText: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.background,
    letterSpacing: 0.2,
  },

  // Email button — secondary (matches sign-up colour palette)
  emailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: Colors.borderLight,
    paddingVertical: 17,
    paddingHorizontal: Spacing.xl,
    gap: 10,
  },
  emailBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.textPrimary,
    letterSpacing: 0.2,
  },

  // Email form
  emailForm: { gap: Spacing.sm },

  backLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: Spacing.xs,
  },
  backLinkText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },

  // Error banner
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 82, 82, 0.10)',
    borderWidth: 1,
    borderColor: 'rgba(255, 82, 82, 0.20)',
    borderRadius: 12,
    padding: Spacing.md,
    gap: Spacing.xs,
    marginBottom: Spacing.xs,
  },
  errorText: {
    ...Typography.bodySmall,
    color: Colors.danger,
    flex: 1,
  },

  // Footer
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.xs,
    paddingBottom: Spacing.sm,
  },
  footerText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  footerLink: {
    ...Typography.bodySmall,
    color: Colors.primary,
    fontWeight: '700',
  },
});
