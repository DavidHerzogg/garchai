/**
 * GARCH AI — Sign Up Screen
 *
 * Redesigned to match the Sign In screen layout:
 *   1. Logo — Garch_Ai_APP_Logo_Background.png in a rounded container
 *   2. Title/Subtitle
 *   3. Illustration (SVG)
 *   4. Form (Registration or OTP Verification)
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Image,
} from 'react-native';
import { useRouter, Link } from 'expo-router';
import { useSignUp, useSSO, useClerk } from '@clerk/expo';
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

export default function SignUpScreen() {
  const { signUp } = useSignUp();
  const { setActive } = useClerk();
  const { startSSOFlow } = useSSO();
  const router = useRouter();

  // Navigation states
  const [pendingVerification, setPendingVerification] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState('');

  // Form states
  const [name, setName] = useState('');
  const [emailAddress, setEmailAddress] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');

  // ── Handle Sign Up (Clerk v3 Signals/Future API) ──────────────────────────
  const onSignUpPress = async () => {
    if (!signUp) return;
    setLoading(true);
    setError('');

    try {
      // Step 1 — create the user
      const { error: createError } = await signUp.create({
        emailAddress,
        firstName: name.split(' ')[0] || name,
        lastName: name.split(' ').slice(1).join(' ') || undefined,
      });
      if (createError) {
        setError(createError.longMessage || createError.message || 'Check your registration details.');
        return;
      }

      // Step 2 — set the password
      const { error: passwordError } = await signUp.password({ password });
      if (passwordError) {
        setError(passwordError.longMessage || passwordError.message || 'Invalid password.');
        return;
      }

      // Step 3 — send verification email
      const { error: sendError } = await signUp.verifications.sendEmailCode();
      if (sendError) {
        setError(sendError.longMessage || sendError.message || 'Could not send verification email.');
        return;
      }

      setPendingVerification(true);
    } catch (err: any) {
      setError(
        err?.errors?.[0]?.longMessage ||
        err?.errors?.[0]?.message ||
        'An unexpected error occurred during sign up.'
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Handle Verification ────────────────────────────────────────────────────
  const onVerifyPress = async () => {
    if (!signUp) return;
    setLoading(true);
    setError('');

    try {
      const { error: verifyError } = await signUp.verifications.verifyEmailCode({ code });
      if (verifyError) {
        setError(verifyError.longMessage || verifyError.message || 'Invalid verification code.');
        return;
      }

      if (signUp.status === 'complete') {
        await setActive({ session: signUp.createdSessionId });
        router.replace('/(tabs)');
      } else {
        setError('Additional verification required. Please try again.');
      }
    } catch (err: any) {
      setError(
        err?.errors?.[0]?.longMessage ||
        err?.errors?.[0]?.message ||
        'Invalid verification code.'
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Handle Google SSO ──────────────────────────────────────────────────────
  const onGoogleSignUpPress = async () => {
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
      setError(err?.errors?.[0]?.message || 'Google Sign-Up failed.');
    } finally {
      setGoogleLoading(false);
    }
  };

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
          {/* ── Logo — matched with Sign In ────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(0).duration(450)} style={styles.logoRow}>
            <View style={styles.logoContainer}>
              <Image
                source={require('@/assets/images/Garch_Ai_APP_Logo_Background.png')}
                style={styles.logo}
                resizeMode="contain"
              />
            </View>
            <Text style={styles.title}>
              {pendingVerification ? 'Verify Email' : 'Create Account'}
            </Text>
            <Text style={styles.subtitle}>
              {pendingVerification 
                ? `Enter the code sent to ${emailAddress}`
                : 'Join the next generation of AI trading'
              }
            </Text>
          </Animated.View>

          {/* ── Illustration ─────────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(80).duration(550)} style={styles.illustrationWrapper}>
            <IllustrationSvg width="100%" height={260} />
          </Animated.View>

          {/* ── Error banner ─────────────────────────────────────────────── */}
          {error ? (
            <Animated.View entering={FadeIn.duration(250)} style={styles.errorBanner}>
              <Ionicons name="alert-circle" size={16} color={Colors.danger} />
              <Text style={styles.errorText}>{error}</Text>
            </Animated.View>
          ) : null}

          {/* ── Form Section ─────────────────────────────────────────────── */}
          <Animated.View entering={FadeInUp.delay(160).duration(450)} style={styles.formSection}>
            {!pendingVerification ? (
              /* Step 1: Registration Form */
              <View style={styles.form}>
                <Input
                  label="Full Name"
                  placeholder="John Doe"
                  value={name}
                  onChangeText={setName}
                  autoCapitalize="words"
                />
                <Input
                  label="Email Address"
                  placeholder="name@example.com"
                  value={emailAddress}
                  onChangeText={setEmailAddress}
                  keyboardType="email-address"
                  autoCapitalize="none"
                />
                <Input
                  label="Password"
                  placeholder="••••••••"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                />
                
                <Button
                  title="Create Account"
                  onPress={onSignUpPress}
                  loading={loading}
                  disabled={!name || !emailAddress || !password || loading}
                  fullWidth
                  size="lg"
                  style={styles.submitBtn}
                />

                <View style={styles.divider}>
                  <View style={styles.dividerLine} />
                  <Text style={styles.dividerText}>OR</Text>
                  <View style={styles.dividerLine} />
                </View>

                <TouchableOpacity
                  style={[styles.googleBtn, googleLoading && styles.btnDisabled]}
                  onPress={onGoogleSignUpPress}
                  disabled={googleLoading}
                >
                  {googleLoading ? (
                    <ActivityIndicator size="small" color={Colors.background} />
                  ) : (
                    <Ionicons name="logo-google" size={20} color={Colors.background} />
                  )}
                  <Text style={styles.googleBtnText}>Continue with Google</Text>
                </TouchableOpacity>
              </View>
            ) : (
              /* Step 2: Verification OTP */
              <View style={styles.form}>
                <Input
                  label="Verification Code"
                  placeholder="123456"
                  value={code}
                  onChangeText={setCode}
                  keyboardType="number-pad"
                />
                
                <Button
                  title="Verify & Join"
                  onPress={onVerifyPress}
                  loading={loading}
                  disabled={code.length < 6 || loading}
                  fullWidth
                  size="lg"
                  style={styles.submitBtn}
                />

                <TouchableOpacity
                  style={styles.resendBtn}
                  onPress={async () => {
                    setError('');
                    try {
                      await signUp?.verifications.sendEmailCode();
                    } catch (err: any) {
                      setError(err?.errors?.[0]?.message || 'Could not resend code.');
                    }
                  }}
                >
                  <Text style={styles.resendText}>Didn't receive a code? Resend</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Footer */}
            {!pendingVerification && (
              <View style={styles.footer}>
                <Text style={styles.footerText}>Already have an account? </Text>
                <Link href="/(auth)/sign-in" asChild>
                  <TouchableOpacity>
                    <Text style={styles.footerLink}>Sign In</Text>
                  </TouchableOpacity>
                </Link>
              </View>
            )}
            
            {pendingVerification && (
              <TouchableOpacity
                style={styles.backBtn}
                onPress={() => setPendingVerification(false)}
              >
                <Text style={styles.backBtnText}>Change Email</Text>
              </TouchableOpacity>
            )}
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
  
  // ── Logo Row ──────────────────────────────────────────────────────────
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
    marginTop: 4,
  },
  title: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  subtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginTop: Spacing.xxs,
    textAlign: 'center',
  },

  // ── Illustration ──────────────────────────────────────────────────────
  illustrationWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    minHeight: 220,
    marginVertical: Spacing.lg,
  },

  // ── Form Section ──────────────────────────────────────────────────────
  formSection: {
    width: '100%',
  },
  form: {
    gap: Spacing.sm,
  },
  submitBtn: {
    marginTop: Spacing.xs,
  },

  // ── Google Button ─────────────────────────────────────────────────────
  googleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.primary,
    borderRadius: 16,
    paddingVertical: 17,
    gap: 10,
  },
  btnDisabled: { opacity: 0.6 },
  googleBtnText: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.background,
  },

  // ── Divider ───────────────────────────────────────────────────────────
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: Spacing.md,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: Colors.border,
  },
  dividerText: {
    ...Typography.caption,
    color: Colors.textTertiary,
    marginHorizontal: Spacing.md,
    fontWeight: '700',
  },

  // ── Error Banner ──────────────────────────────────────────────────────
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 82, 82, 0.10)',
    borderWidth: 1,
    borderColor: 'rgba(255, 82, 82, 0.20)',
    borderRadius: 12,
    padding: Spacing.md,
    gap: Spacing.xs,
    marginBottom: Spacing.md,
  },
  errorText: {
    ...Typography.bodySmall,
    color: Colors.danger,
    flex: 1,
  },

  // ── Footer & Buttons ──────────────────────────────────────────────────
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.md,
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
  resendBtn: {
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  resendText: {
    ...Typography.bodySmall,
    color: Colors.primary,
  },
  backBtn: {
    alignItems: 'center',
    marginTop: Spacing.md,
  },
  backBtnText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
});
