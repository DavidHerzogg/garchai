/**
 * GARCH AI — Root Layout
 *
 * Wraps the entire app with:
 * - SafeAreaProvider  (must be outermost UI wrapper)
 * - ClerkProvider     (authentication)
 * - ConvexProviderWithClerk (backend + auth bridge)
 * - Font loading (Inter)
 * - Dark theme
 * - Error boundary
 *
 * WebBrowser.maybeCompleteAuthSession() is called here at module level so
 * that it runs exactly once before any screen mounts, eliminating the
 * "redirect handler set when it should not be" OAuth session conflict.
 */
import React, { useEffect } from 'react';
import { View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as WebBrowser from 'expo-web-browser';
import * as SystemUI from 'expo-system-ui';
import { useFonts, Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold } from '@expo-google-fonts/inter';
import { SplashScreen, Stack, useRouter, useSegments } from 'expo-router';
import { ClerkProvider, ClerkLoaded, useAuth } from '@clerk/expo';
import { tokenCache } from '@clerk/expo/token-cache';
import { ConvexReactClient } from 'convex/react';
import { ConvexProviderWithClerk } from 'convex/react-clerk';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider, DarkTheme } from '@react-navigation/native';
import { Colors } from '@/constants/Colors';

export { ErrorBoundary } from 'expo-router';

// ─── OAuth Session Cleanup ───────────────────────────────────────────────────
// Must run at module level (app entry), not inside a component.
// This completes any pending OAuth redirect that is still in the WebBrowser
// session cache and clears the redirect handler — preventing the
// "invalid state with a redirect handler set" error.
WebBrowser.maybeCompleteAuthSession();

// ─── Protected Routes Gate ───────────────────────────────────────────────────
function useProtectedRoute(isLoaded: boolean, isSignedIn: boolean) {
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (!isLoaded) return;

    const inAuthGroup = segments[0] === '(auth)';

    if (!isSignedIn && !inAuthGroup) {
      router.replace('/(auth)/sign-in');
    } else if (isSignedIn && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [isSignedIn, isLoaded, segments]);
}

export const unstable_settings = {
  initialRouteName: '(auth)',
};

SplashScreen.preventAutoHideAsync();

const convex = new ConvexReactClient(
  process.env.EXPO_PUBLIC_CONVEX_URL || 'https://placeholder.convex.cloud',
  { unsavedChangesWarning: false }
);

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
  });

  // Force system UI background to match app theme (prevents white flashes)
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(Colors.background);
  }, []);

  useEffect(() => {
    if (fontError) {
      console.error('Font loading error:', fontError);
    }
  }, [fontError]);

  useEffect(() => {
    if (fontsLoaded || fontError) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) {
    return <View style={{ flex: 1, backgroundColor: Colors.background }} />;
  }

  const clerkPublishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;

  if (!clerkPublishableKey) {
    throw new Error(
      'Missing EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY in .env file. ' +
      'Add your Clerk Publishable Key to continue.'
    );
  }

  return (
    // SafeAreaProvider must be the outermost UI wrapper so that
    // useSafeAreaInsets() works correctly everywhere in the tree.
    <View style={{ flex: 1, backgroundColor: Colors.background }}>
      <SafeAreaProvider>
        <ClerkProvider publishableKey={clerkPublishableKey} tokenCache={tokenCache}>
          <ClerkLoaded>
            <ConvexProviderWithClerk client={convex} useAuth={useAuth}>
              <RootLayoutNav />
            </ConvexProviderWithClerk>
          </ClerkLoaded>
        </ClerkProvider>
      </SafeAreaProvider>
    </View>
  );
}

const AppTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: Colors.background,
    card: Colors.surface,
    text: Colors.textPrimary,
    border: Colors.border,
    notification: Colors.primary,
  },
};

function RootLayoutNav() {
  const { isLoaded, isSignedIn } = useAuth();
  useProtectedRoute(isLoaded, !!isSignedIn);

  return (
    <ThemeProvider value={AppTheme}>
      <StatusBar style="light" translucent backgroundColor="transparent" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: Colors.background },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
      </Stack>


    </ThemeProvider>
  );
}
