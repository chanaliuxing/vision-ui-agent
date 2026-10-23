// server/src/billing.js
// Billing and subscription management API
import express from "express";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import { createCheckoutSession, createPortalSession } from "./payments/index.js";

export const billing = express.Router();

// Get current subscription and billing info
billing.get("/info", authRequired, async (req, res) => {
  try {
    const user_id = req.user.user_id;

    // Get current subscription
    const { rows: subs } = await pool.query(`
      select s.*, p.name as plan_name, p.description as plan_description,
             p.device_limit, p.hp_concurrency, p.monthly_price_usd
      from subscriptions s
      join plan_products p on p.key = s.plan
      where s.user_id = $1 and s.status = 'active'
      order by s.created_at desc limit 1
    `, [user_id]);

    // Get wallet balance
    const { rows: wallets } = await pool.query(
      "select balance_cents, currency from wallets where user_id = $1",
      [user_id]
    );

    // Get billing limits
    const { rows: limits } = await pool.query(
      "select soft_cap_cents, hard_cap_cents from billing_limits where user_id = $1",
      [user_id]
    );

    // Get current period usage
    const currentPeriodStart = new Date();
    currentPeriodStart.setDate(1);
    currentPeriodStart.setHours(0, 0, 0, 0);

    const { rows: usage } = await pool.query(`
      select coalesce(sum(total_cents), 0) as current_period_total
      from invoices
      where user_id = $1 and period_start >= $2 and status in ('open', 'draft')
    `, [user_id, currentPeriodStart]);

    res.json({
      subscription: subs[0] || null,
      wallet: wallets[0] || { balance_cents: 0, currency: 'usd' },
      limits: limits[0] || { soft_cap_cents: 5000, hard_cap_cents: 10000 },
      usage: {
        current_period_total: parseInt(usage[0]?.current_period_total || 0),
        period_start: currentPeriodStart.toISOString()
      }
    });
  } catch (error) {
    console.error("Get billing info error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// List available plans
billing.get("/plans", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select * from plan_products order by monthly_price_usd asc"
    );
    res.json({ plans: rows });
  } catch (error) {
    console.error("List plans error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Create checkout session for subscription
billing.post("/checkout", authRequired, async (req, res) => {
  try {
    const { plan_key, mode = "subscription" } = req.body || {};
    if (!plan_key) return res.status(400).json({ error: "plan_key required" });

    // Validate plan exists
    const { rows: plans } = await pool.query(
      "select * from plan_products where key = $1",
      [plan_key]
    );
    if (!plans.length) return res.status(400).json({ error: "invalid plan" });

    // Get user info
    const { rows: users } = await pool.query(
      "select id, email, stripe_customer_id from users where id = $1",
      [req.user.user_id]
    );
    const user = users[0];

    const urls = {
      success_url: (process.env.APP_URL || "http://localhost:3000") + "/billing/success",
      cancel_url: (process.env.APP_URL || "http://localhost:3000") + "/billing/cancel"
    };

    const { url } = await createCheckoutSession({
      user,
      plan: plan_key,
      mode,
      ...urls
    });

    res.json({ url });
  } catch (error) {
    console.error("Create checkout error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Create billing portal session
billing.post("/portal", authRequired, async (req, res) => {
  try {
    const { rows: users } = await pool.query(
      "select id, email, stripe_customer_id from users where id = $1",
      [req.user.user_id]
    );
    const user = users[0];

    if (!user.stripe_customer_id) {
      return res.status(400).json({ error: "no billing account found" });
    }

    const { url } = await createPortalSession({
      user,
      return_url: (process.env.APP_URL || "http://localhost:3000") + "/app"
    });

    res.json({ url });
  } catch (error) {
    console.error("Create portal error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// List invoices
billing.get("/invoices", authRequired, async (req, res) => {
  try {
    const { limit = 50 } = req.query;
    const { rows } = await pool.query(`
      select i.*,
             count(il.id) as line_count,
             array_agg(il.description) filter (where il.description is not null) as line_descriptions
      from invoices i
      left join invoice_lines il on il.invoice_id = i.id
      where i.user_id = $1
      group by i.id
      order by i.created_at desc
      limit $2
    `, [req.user.user_id, Math.min(parseInt(limit), 100)]);

    res.json({ invoices: rows });
  } catch (error) {
    console.error("List invoices error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get invoice details with lines
billing.get("/invoices/:id", authRequired, async (req, res) => {
  try {
    const { rows: invoices } = await pool.query(
      "select * from invoices where id = $1 and user_id = $2",
      [req.params.id, req.user.user_id]
    );

    if (!invoices.length) {
      return res.status(404).json({ error: "invoice not found" });
    }

    const { rows: lines } = await pool.query(
      "select * from invoice_lines where invoice_id = $1 order by kind, description",
      [req.params.id]
    );

    res.json({
      invoice: invoices[0],
      lines
    });
  } catch (error) {
    console.error("Get invoice error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Wallet operations
billing.get("/wallet", authRequired, async (req, res) => {
  try {
    const { rows: wallets } = await pool.query(
      "select balance_cents, currency, updated_at from wallets where user_id = $1",
      [req.user.user_id]
    );

    const { rows: txns } = await pool.query(
      "select * from wallet_txns where user_id = $1 order by created_at desc limit 20",
      [req.user.user_id]
    );

    res.json({
      wallet: wallets[0] || { balance_cents: 0, currency: 'usd' },
      transactions: txns
    });
  } catch (error) {
    console.error("Get wallet error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Update billing limits (admin only)
billing.put("/limits", authRequired, async (req, res) => {
  try {
    // Simple check - in production you'd check admin role
    const { soft_cap_cents, hard_cap_cents } = req.body || {};
    if (typeof soft_cap_cents !== 'number' || typeof hard_cap_cents !== 'number') {
      return res.status(400).json({ error: "invalid limits" });
    }

    if (soft_cap_cents >= hard_cap_cents) {
      return res.status(400).json({ error: "soft cap must be less than hard cap" });
    }

    await pool.query(`
      insert into billing_limits (user_id, soft_cap_cents, hard_cap_cents)
      values ($1, $2, $3)
      on conflict (user_id) do update set
        soft_cap_cents = excluded.soft_cap_cents,
        hard_cap_cents = excluded.hard_cap_cents
    `, [req.user.user_id, soft_cap_cents, hard_cap_cents]);

    res.json({
      message: "limits updated",
      soft_cap_cents,
      hard_cap_cents
    });
  } catch (error) {
    console.error("Update limits error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});