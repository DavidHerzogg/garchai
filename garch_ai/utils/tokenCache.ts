/**
 * Clerk token cache — re-exported from @clerk/expo v3.
 *
 * Clerk v3 provides its own optimized token cache via
 * `@clerk/expo/token-cache` that uses expo-secure-store internally.
 *
 * This file exists for backward compatibility with any
 * imports of `@/utils/tokenCache`.
 */
export { tokenCache } from '@clerk/expo/token-cache';
