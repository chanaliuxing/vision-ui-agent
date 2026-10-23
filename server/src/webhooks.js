// server/src/webhooks.js
// Payment webhook handlers
import express from "express";
import { verifyWebhook } from "./payments/index.js";
import { pool } from "./db.js";

export const webhooks = express.Router();

// Stripe webhook handler
webhooks.post("/stripe", express.raw({ type: "application/json" }), async (req, res) => {
  let event;
  try {
    event = verifyWebhook(req.body, req.headers['stripe-signature'] || 'mock_sig');
  } catch (err) {
    console.error("Webhook signature verification failed:", err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  try {
    switch (event.type) {
      case "checkout.session.completed":
        await handleCheckoutCompleted(event.data.object);
        break;

      case "invoice.payment_succeeded":
        await handleInvoicePaymentSucceeded(event.data.object);
        break;

      case "invoice.payment_failed":
        await handleInvoicePaymentFailed(event.data.object);
        break;

      case "customer.subscription.updated":
        await handleSubscriptionUpdated(event.data.object);
        break;

      case "customer.subscription.deleted":
        await handleSubscriptionDeleted(event.data.object);
        break;

      default:
        console.log(`Unhandled event type: ${event.type}`);
    }

    res.json({ received: true });
  } catch (error) {
    console.error("Webhook processing error:", error);
    res.status(500).json({ error: "webhook processing failed" });
  }
});

async function handleCheckoutCompleted(session) {
  console.log("Processing checkout completion:", session.id);

  const userId = session.metadata?.user_id;
  const planKey = session.metadata?.plan_key;

  if (!userId || !planKey) {
    console.error("Missing metadata in checkout session");
    return;
  }

  // Get plan details
  const { rows: plans } = await pool.query(
    "select * from plan_products where key = $1",
    [planKey]
  );

  if (!plans.length) {
    console.error(`Plan ${planKey} not found`);
    return;
  }

  const plan = plans[0];

  // Create or update subscription
  const billingCycleStart = new Date();
  const billingCycleEnd = new Date();
  billingCycleEnd.setMonth(billingCycleEnd.getMonth() + 1);

  await pool.query(`
    insert into subscriptions (user_id, plan, device_limit, hp_concurrency, status, external_sub_id, billing_cycle_start, billing_cycle_end)
    values ($1, $2, $3, $4, 'active', $5, $6, $7)
    on conflict (user_id) do update set
      plan = excluded.plan,
      device_limit = excluded.device_limit,
      hp_concurrency = excluded.hp_concurrency,
      status = excluded.status,
      external_sub_id = excluded.external_sub_id,
      billing_cycle_start = excluded.billing_cycle_start,
      billing_cycle_end = excluded.billing_cycle_end
  `, [userId, planKey, plan.device_limit, plan.hp_concurrency, session.subscription || session.id, billingCycleStart, billingCycleEnd]);

  // Create initial invoice for the subscription
  await createSubscriptionInvoice(userId, plan, billingCycleStart, billingCycleEnd);

  console.log(`Subscription created/updated for user ${userId}, plan ${planKey}`);
}

async function handleInvoicePaymentSucceeded(invoice) {
  console.log("Processing invoice payment success:", invoice.id);

  // Mark corresponding invoice as paid
  await pool.query(
    "update invoices set status = 'paid', paid_at = now() where external_invoice_id = $1",
    [invoice.id]
  );

  // Record payment
  const { rows: invoices } = await pool.query(
    "select user_id, total_cents from invoices where external_invoice_id = $1",
    [invoice.id]
  );

  if (invoices.length) {
    const { user_id, total_cents } = invoices[0];
    await pool.query(`
      insert into payments (user_id, provider, external_payment_id, currency, amount_cents, status)
      values ($1, 'stripe', $2, 'usd', $3, 'succeeded')
    `, [user_id, invoice.payment_intent, total_cents]);
  }

  console.log(`Invoice ${invoice.id} marked as paid`);
}

async function handleInvoicePaymentFailed(invoice) {
  console.log("Processing invoice payment failure:", invoice.id);

  // Mark invoice as uncollectible or open depending on attempts
  const status = invoice.attempt_count >= 3 ? 'uncollectible' : 'open';

  await pool.query(
    "update invoices set status = $1 where external_invoice_id = $2",
    [status, invoice.id]
  );

  // If uncollectible, consider suspending subscription
  if (status === 'uncollectible') {
    const { rows: invoices } = await pool.query(
      "select user_id from invoices where external_invoice_id = $1",
      [invoice.id]
    );

    if (invoices.length) {
      await pool.query(
        "update subscriptions set status = 'past_due' where user_id = $1",
        [invoices[0].user_id]
      );
    }
  }

  console.log(`Invoice ${invoice.id} payment failed, status: ${status}`);
}

async function handleSubscriptionUpdated(subscription) {
  console.log("Processing subscription update:", subscription.id);

  // Find user by external_sub_id and update subscription details
  await pool.query(`
    update subscriptions set
      status = $1,
      billing_cycle_start = $2,
      billing_cycle_end = $3
    where external_sub_id = $4
  `, [
    subscription.status,
    new Date(subscription.current_period_start * 1000),
    new Date(subscription.current_period_end * 1000),
    subscription.id
  ]);

  console.log(`Subscription ${subscription.id} updated`);
}

async function handleSubscriptionDeleted(subscription) {
  console.log("Processing subscription deletion:", subscription.id);

  await pool.query(
    "update subscriptions set status = 'canceled' where external_sub_id = $1",
    [subscription.id]
  );

  console.log(`Subscription ${subscription.id} canceled`);
}

async function createSubscriptionInvoice(userId, plan, periodStart, periodEnd) {
  // Create invoice for subscription
  const { rows: invoices } = await pool.query(`
    insert into invoices (user_id, period_start, period_end, status, subtotal_cents, total_cents)
    values ($1, $2, $3, 'open', $4, $4)
    returning id
  `, [userId, periodStart, periodEnd, Math.round(plan.monthly_price_usd * 100)]);

  const invoiceId = invoices[0].id;

  // Add subscription line item
  await pool.query(`
    insert into invoice_lines (invoice_id, kind, description, quantity, unit_amount_cents, amount_cents)
    values ($1, 'subscription', $2, 1, $3, $3)
  `, [invoiceId, `${plan.name} - Monthly Subscription`, Math.round(plan.monthly_price_usd * 100), Math.round(plan.monthly_price_usd * 100)]);

  return invoiceId;
}