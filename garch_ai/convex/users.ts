import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

/**
 * GARCH AI — User management.
 *
 * Syncs users from Clerk and manages subscription state.
 */

// ────────────────────────────────────────────────────────
// SYNC — create or update user from Clerk data
// ────────────────────────────────────────────────────────
export const sync = mutation({
  args: {
    clerkId: v.string(),
    email: v.string(),
    name: v.optional(v.string()),
    imageUrl: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("users")
      .withIndex("by_clerk_id", (q) => q.eq("clerkId", args.clerkId))
      .first();

    const now = Date.now();
    const today = new Date().toISOString().split("T")[0];

    if (existing) {
      // Update existing user
      await ctx.db.patch(existing._id, {
        email: args.email,
        name: args.name,
        imageUrl: args.imageUrl,
        updatedAt: now,
      });
      return existing._id;
    }

    // Create new user
    const userId = await ctx.db.insert("users", {
      clerkId: args.clerkId,
      email: args.email,
      name: args.name,
      imageUrl: args.imageUrl,
      tier: "free",
      backtestsUsedToday: 0,
      backtestsResetDate: today,
      createdAt: now,
      updatedAt: now,
    });

    return userId;
  },
});

// ────────────────────────────────────────────────────────
// GET BY CLERK ID — find user by their Clerk ID
// ────────────────────────────────────────────────────────
export const getByClerkId = query({
  args: { clerkId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_clerk_id", (q) => q.eq("clerkId", args.clerkId))
      .first();
  },
});

// ────────────────────────────────────────────────────────
// GET — fetch user by ID
// ────────────────────────────────────────────────────────
export const get = query({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.id);
  },
});

// ────────────────────────────────────────────────────────
// UPDATE TIER — change subscription tier
// ────────────────────────────────────────────────────────
export const updateTier = mutation({
  args: {
    id: v.id("users"),
    tier: v.union(
      v.literal("free"),
      v.literal("pro"),
      v.literal("premium")
    ),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      tier: args.tier,
      updatedAt: Date.now(),
    });
  },
});

// ────────────────────────────────────────────────────────
// INCREMENT BACKTEST COUNT — track daily usage
// ────────────────────────────────────────────────────────
export const incrementBacktestCount = mutation({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    const user = await ctx.db.get(args.id);
    if (!user) throw new Error("User not found");

    const today = new Date().toISOString().split("T")[0];

    if (user.backtestsResetDate !== today) {
      // New day — reset counter
      await ctx.db.patch(args.id, {
        backtestsUsedToday: 1,
        backtestsResetDate: today,
        updatedAt: Date.now(),
      });
    } else {
      await ctx.db.patch(args.id, {
        backtestsUsedToday: user.backtestsUsedToday + 1,
        updatedAt: Date.now(),
      });
    }
  },
});

// ────────────────────────────────────────────────────────
// CHECK BACKTEST LIMIT — verify user hasn't exceeded daily limit
// ────────────────────────────────────────────────────────
export const checkBacktestLimit = query({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    const user = await ctx.db.get(args.id);
    if (!user) return { allowed: false, reason: "User not found" };

    const today = new Date().toISOString().split("T")[0];
    const count = user.backtestsResetDate === today ? user.backtestsUsedToday : 0;

    const limits: Record<string, number> = {
      free: 3,
      pro: 25,
      premium: 999,
    };

    const limit = limits[user.tier] || 3;
    const remaining = Math.max(0, limit - count);

    return {
      allowed: count < limit,
      used: count,
      limit,
      remaining,
      tier: user.tier,
    };
  },
});
