import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

/**
 * GARCH AI — Convex Database Schema
 *
 * Tables:
 * - users: Clerk-synced user data + subscription info
 * - strategies: Complete strategy definitions
 * - backtests: Job queue for backtest execution
 * - results: Cached backtest results
 */
export default defineSchema({
  // ────────────────────────────────────────────────────────
  // Users — synced from Clerk via webhook or on first login
  // ────────────────────────────────────────────────────────
  users: defineTable({
    clerkId: v.string(),
    email: v.string(),
    name: v.optional(v.string()),
    imageUrl: v.optional(v.string()),
    tier: v.union(
      v.literal("free"),
      v.literal("pro"),
      v.literal("premium")
    ),
    backtestsUsedToday: v.number(),
    backtestsResetDate: v.string(), // ISO date string
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_clerk_id", ["clerkId"])
    .index("by_email", ["email"]),

  strategies: defineTable({
    userId: v.id("users"),
    prompt: v.string(),
    equity: v.array(v.number()),
    createdAt: v.number(),
  }).index("by_user", ["userId"]),
});

