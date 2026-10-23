// server/billing_worker.js
// Usage aggregation worker for Stage 9 billing system
import { pool } from "./src/db.js";
import { tokensToCents } from "./src/payments/stripe.js";

/**
 * Aggregate usage for a specific user and time period
 */
async function rollupPeriod(user_id, start, end) {
  console.log(`[billing] Aggregating usage for user ${user_id} from ${start} to ${end}`);

  const q = `
    select provider, model,
           sum(prompt_tokens) as p, sum(completion_tokens) as c
    from llm_usage
    where user_id=$1 and ts >= $2 and ts < $3
    group by provider, model`;

  const { rows } = await pool.query(q, [user_id, start, end]);

  for (const r of rows) {
    // Convert tokens to cents using pricing logic
    const cents = tokensToCents(r.provider, r.model, r.p, r.c, "usd");

    console.log(`[billing] ${r.provider}/${r.model}: ${r.p}+${r.c} tokens = ${cents} cents`);

    await pool.query(`
      insert into usage_rollups(user_id, period_start, period_end, provider, model, prompt_tokens, completion_tokens, amount_cents)
      values($1, $2, $3, $4, $5, $6, $7, $8)
      on conflict(user_id, period_start, period_end, provider, model)
      do update set
        prompt_tokens = excluded.prompt_tokens,
        completion_tokens = excluded.completion_tokens,
        amount_cents = excluded.amount_cents
    `, [user_id, start, end, r.provider, r.model, r.p, r.c, cents]);
  }
}

/**
 * Ensure an open invoice exists for the given period
 */
async function ensureOpenInvoice(user_id, start, end) {
  const q = `select * from invoices where user_id=$1 and period_start=$2 and period_end=$3`;
  const { rows } = await pool.query(q, [user_id, start, end]);

  if (rows.length) return rows[0];

  const ins = await pool.query(
    `insert into invoices(user_id, period_start, period_end, status, currency, subtotal_cents, total_cents)
     values($1, $2, $3, 'open', 'usd', 0, 0) returning *`,
    [user_id, start, end]
  );

  console.log(`[billing] Created new invoice ${ins.rows[0].id} for user ${user_id}`);
  return ins.rows[0];
}

/**
 * Add or update invoice lines for subscription and usage
 */
async function upsertInvoiceLines(user_id, inv) {
  console.log(`[billing] Updating invoice lines for invoice ${inv.id}`);

  // Clear existing lines for this invoice
  await pool.query(`delete from invoice_lines where invoice_id = $1`, [inv.id]);

  // Add subscription fee
  const sub = await pool.query(`
    select s.plan, p.monthly_price_usd, p.name
    from subscriptions s
    join plan_products p on p.key = s.plan
    where s.user_id = $1 and s.status = 'active'
    order by s.created_at desc limit 1
  `, [user_id]);

  if (sub.rowCount) {
    const priceCents = Math.round(Number(sub.rows[0].monthly_price_usd) * 100);
    await addLine(inv.id, 'subscription', `${sub.rows[0].name} - Monthly Subscription`, 1, priceCents, priceCents);
    console.log(`[billing] Added subscription line: ${priceCents} cents`);
  }

  // Add usage fees
  const rolls = await pool.query(`
    select provider, model, amount_cents, prompt_tokens, completion_tokens
    from usage_rollups
    where user_id = $1 and period_start = $2 and period_end = $3
  `, [user_id, inv.period_start, inv.period_end]);

  for (const r of rolls.rows) {
    if (r.amount_cents > 0) {
      await addLine(inv.id, 'usage', `${r.provider}/${r.model} - ${r.prompt_tokens + r.completion_tokens} tokens`, 1, r.amount_cents, r.amount_cents);
      console.log(`[billing] Added usage line: ${r.provider}/${r.model} = ${r.amount_cents} cents`);
    }
  }

  // Update invoice totals
  await pool.query(`
    update invoices set
      subtotal_cents = (select coalesce(sum(amount_cents), 0) from invoice_lines where invoice_id = $1),
      total_cents = (select coalesce(sum(amount_cents), 0) from invoice_lines where invoice_id = $1)
    where id = $1
  `, [inv.id]);

  // Get updated totals
  const updated = await pool.query(`select subtotal_cents, total_cents from invoices where id = $1`, [inv.id]);
  console.log(`[billing] Invoice ${inv.id} totals: subtotal=${updated.rows[0].subtotal_cents}, total=${updated.rows[0].total_cents} cents`);
}

/**
 * Add a line item to an invoice
 */
async function addLine(invoice_id, kind, desc, qty, unit_cents, amount_cents) {
  await pool.query(
    `insert into invoice_lines(invoice_id, kind, description, quantity, unit_amount_cents, amount_cents)
     values($1, $2, $3, $4, $5, $6)`,
    [invoice_id, kind, desc, qty, unit_cents, amount_cents]
  );
}

/**
 * Get current billing period (month-to-month)
 */
function getCurrentPeriod() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);

  return {
    start: start.toISOString(),
    end: end.toISOString()
  };
}

/**
 * Main billing aggregation process
 */
async function main() {
  try {
    console.log("[billing] Starting usage aggregation worker...");

    const period = getCurrentPeriod();
    console.log(`[billing] Processing period: ${period.start} to ${period.end}`);

    // Get all active users
    const users = await pool.query(`
      select distinct u.id
      from users u
      where u.status = 1
    `);

    console.log(`[billing] Found ${users.rowCount} active users to process`);

    for (const u of users.rows) {
      try {
        console.log(`[billing] Processing user ${u.id}...`);

        // Aggregate usage for this period
        await rollupPeriod(u.id, period.start, period.end);

        // Ensure invoice exists
        const inv = await ensureOpenInvoice(u.id, period.start, period.end);

        // Update invoice lines
        await upsertInvoiceLines(u.id, inv);

        console.log(`[billing] Completed processing for user ${u.id}`);
      } catch (error) {
        console.error(`[billing] Error processing user ${u.id}:`, error);
      }
    }

    console.log("[billing] Usage aggregation completed successfully");
  } catch (error) {
    console.error("[billing] Fatal error in billing worker:", error);
    throw error;
  }
}

// Handle being run directly vs imported
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => {
    console.error(e);
    process.exit(1);
  });
}

export { rollupPeriod, ensureOpenInvoice, upsertInvoiceLines, main };