import { v } from "convex/values";
import { query, mutation } from "./_generated/server";

export const list = query({
  args: { userId: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("strategies")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .order("desc")
      .collect();
  },
});

export const create = mutation({
  args: { 
    userId: v.id("users"),
    prompt: v.string(),
    equity: v.array(v.number()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("strategies", {
      userId: args.userId,
      prompt: args.prompt,
      equity: args.equity,
      createdAt: Date.now(),
    });
  },
});
