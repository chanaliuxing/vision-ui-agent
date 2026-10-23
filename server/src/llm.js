// server/src/llm.js
// LLM API Key management and routing
import express from "express";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import { encryptKey } from "./crypto.js";

export const llm = express.Router();

// Create API key (supports both PLAINTEXT and ENCRYPTED modes)
llm.post("/keys", authRequired, async (req, res) => {
  try {
    const { provider, name, api_key, mode } = req.body || {};
    if (!provider || !api_key) return res.status(400).json({ error: "bad params" });

    const m = (mode || process.env.DEFAULT_KEY_MODE || "ENCRYPTED").toUpperCase();
    const last4 = api_key.slice(-4);

    let cols, vals;
    const returning = "id,last4,provider,name,mode";

    if (m === "PLAINTEXT") {
      cols = "user_id,provider,name,mode,plaintext_key,last4,created_by";
      vals = [req.user.user_id, provider, name || null, "PLAINTEXT", api_key, last4, req.user.user_id];
    } else {
      const { enc, iv, tag } = encryptKey(api_key);
      cols = "user_id,provider,name,mode,enc_key,iv,tag,last4,created_by";
      vals = [req.user.user_id, provider, name || null, "ENCRYPTED",
              enc.toString("base64"), iv.toString("base64"), tag.toString("base64"), last4, req.user.user_id];
    }

    const placeholder = vals.map((_, i) => '$' + (i + 1)).join(',');
    const { rows } = await pool.query(
      `insert into user_api_keys(${cols}) values(${placeholder}) returning ${returning}`,
      vals
    );

    res.json({ key: rows[0] });
  } catch (error) {
    console.error("Create key error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// List user's API keys (never returns plaintext)
llm.get("/keys", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select id,provider,name,last4,mode,created_at from user_api_keys where user_id=$1 order by created_at desc",
      [req.user.user_id]
    );
    res.json({ keys: rows });
  } catch (error) {
    console.error("List keys error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Delete API key
llm.delete("/keys/:id", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "delete from user_api_keys where id=$1 and user_id=$2 returning id",
      [req.params.id, req.user.user_id]
    );
    if (!rows.length) return res.status(404).json({ error: "not found" });
    res.json({ deleted: rows[0].id });
  } catch (error) {
    console.error("Delete key error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Submit LLM job with billing and rate limiting
llm.post("/submit", authRequired, async (req, res) => {
  try {
    const { job_type, prompt_pack_key, schema_key, inputs, provider, model } = req.body || {};
    if (!job_type) return res.status(400).json({ error: "job_type required" });

    const user_id = req.user.user_id;

    // Step 1: Check billing limits and wallet balance
    const billingCheck = await checkBillingLimits(user_id, provider || 'gemini', model || 'gemini-1.5-flash');
    if (!billingCheck.allowed) {
      await pool.query(
        "insert into llm_jobs(user_id,job_type,prompt_pack_key,schema_key,status,error_message) values($1,$2,$3,$4,'failed',$5)",
        [user_id, job_type, prompt_pack_key || null, schema_key || null, billingCheck.reason]
      );
      return res.status(402).json({
        error: "Payment Required",
        reason: billingCheck.reason,
        soft_cap_warning: billingCheck.soft_cap_warning
      });
    }

    // Step 2: Create job record
    const { rows } = await pool.query(
      "insert into llm_jobs(user_id,job_type,prompt_pack_key,schema_key,provider,model,status) values($1,$2,$3,$4,$5,$6,'pending') returning id",
      [user_id, job_type, prompt_pack_key || null, schema_key || null, provider || 'gemini', model || 'gemini-1.5-flash']
    );

    const job_id = rows[0].id;

    // Step 3: Send soft cap warning if needed
    if (billingCheck.soft_cap_warning) {
      console.warn(`[billing] Soft cap warning for user ${user_id}: ${billingCheck.soft_cap_warning}`);
      // In production, send email/notification here
    }

    // In a real implementation, this would be sent to SQS for worker processing
    res.json({
      job_id,
      status: "submitted",
      message: "Job queued for processing",
      billing_status: billingCheck.billing_status
    });
  } catch (error) {
    console.error("Submit job error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get job status
llm.get("/jobs/:id", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select id,job_type,provider,model,status,input_tokens,output_tokens,cost_cents,created_at,completed_at from llm_jobs where id=$1 and user_id=$2",
      [req.params.id, req.user.user_id]
    );
    if (!rows.length) return res.status(404).json({ error: "not found" });
    res.json({ job: rows[0] });
  } catch (error) {
    console.error("Get job error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Prompt Pack management
llm.post("/prompt_packs", authRequired, async (req, res) => {
  try {
    const { key, revision, content, variables } = req.body || {};
    if (!key || !content) return res.status(400).json({ error: "key and content required" });

    const { rows } = await pool.query(
      "insert into prompt_packs(key,revision,content,variables) values($1,$2,$3,$4) returning id,key,revision",
      [key, revision || 1, content, variables || []]
    );

    res.json({ prompt_pack: rows[0] });
  } catch (error) {
    if (error.code === '23505') {
      return res.status(409).json({ error: "key and revision already exists" });
    }
    console.error("Create prompt pack error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Schema management
llm.post("/schemas", authRequired, async (req, res) => {
  try {
    const { key, revision, schema } = req.body || {};
    if (!key || !schema) return res.status(400).json({ error: "key and schema required" });

    const { rows } = await pool.query(
      "insert into llm_schemas(key,revision,schema) values($1,$2,$3) returning id,key,revision",
      [key, revision || 1, schema]
    );

    res.json({ schema: rows[0] });
  } catch (error) {
    if (error.code === '23505') {
      return res.status(409).json({ error: "key and revision already exists" });
    }
    console.error("Create schema error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Policy management
llm.post("/policies", authRequired, async (req, res) => {
  try {
    const { job_type, strategy } = req.body || {};
    if (!job_type || !strategy) return res.status(400).json({ error: "job_type and strategy required" });

    const { rows } = await pool.query(
      "insert into llm_policies(job_type,strategy) values($1,$2) on conflict(job_type) do update set strategy=excluded.strategy,updated_at=now() returning id,job_type,strategy",
      [job_type, strategy]
    );

    res.json({ policy: rows[0] });
  } catch (error) {
    console.error("Create policy error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get routing policies
llm.get("/policies", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select job_type,strategy,updated_at from llm_policies order by job_type"
    );
    res.json({ policies: rows });
  } catch (error) {
    console.error("Get policies error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

/**
 * Check billing limits and wallet balance before processing LLM jobs
 */
async function checkBillingLimits(user_id, provider, model) {
  try {
    // Step 1: Get user's wallet balance and billing limits
    const { rows: wallets } = await pool.query(
      "select balance_cents from wallets where user_id = $1",
      [user_id]
    );

    const { rows: limits } = await pool.query(
      "select soft_cap_cents, hard_cap_cents from billing_limits where user_id = $1",
      [user_id]
    );

    const wallet_balance = wallets[0]?.balance_cents || 0;
    const soft_cap = limits[0]?.soft_cap_cents || 5000; // Default $50
    const hard_cap = limits[0]?.hard_cap_cents || 10000; // Default $100

    // Step 2: Estimate job cost (conservative estimate)
    const estimatedCents = estimateJobCost(provider, model);

    // Step 3: Check wallet balance first (preferred payment method)
    if (wallet_balance >= estimatedCents) {
      return {
        allowed: true,
        billing_status: 'wallet_sufficient',
        estimated_cost_cents: estimatedCents
      };
    }

    // Step 4: Check current period accumulated costs
    const currentPeriodStart = new Date();
    currentPeriodStart.setDate(1);
    currentPeriodStart.setHours(0, 0, 0, 0);

    const { rows: usage } = await pool.query(`
      select coalesce(sum(total_cents), 0) as current_total
      from invoices
      where user_id = $1 and period_start >= $2 and status in ('open', 'draft')
    `, [user_id, currentPeriodStart]);

    const currentTotal = parseInt(usage[0]?.current_total || 0);
    const projectedTotal = currentTotal + estimatedCents;

    // Step 5: Apply limits
    if (projectedTotal >= hard_cap) {
      return {
        allowed: false,
        reason: `Hard cap exceeded. Current: $${(currentTotal/100).toFixed(2)}, Estimated: $${(estimatedCents/100).toFixed(2)}, Limit: $${(hard_cap/100).toFixed(2)}`,
        current_total_cents: currentTotal,
        estimated_cost_cents: estimatedCents,
        hard_cap_cents: hard_cap
      };
    }

    let soft_cap_warning = null;
    if (projectedTotal >= soft_cap) {
      soft_cap_warning = `Soft cap reached. Current: $${(currentTotal/100).toFixed(2)}, Projected: $${(projectedTotal/100).toFixed(2)}, Soft limit: $${(soft_cap/100).toFixed(2)}`;
    }

    return {
      allowed: true,
      billing_status: 'subscription_billing',
      estimated_cost_cents: estimatedCents,
      current_total_cents: currentTotal,
      soft_cap_warning
    };

  } catch (error) {
    console.error("Billing check error:", error);
    // Default to allow on error to prevent service disruption
    return {
      allowed: true,
      billing_status: 'check_failed',
      error: error.message
    };
  }
}

/**
 * Estimate LLM job cost based on provider and model
 */
function estimateJobCost(provider, model) {
  // Conservative estimates for token costs (in cents)
  // This would be more sophisticated in production
  const estimates = {
    gemini: {
      'gemini-1.5-flash': 100,  // $1.00 estimate
      'gemini-pro': 200
    },
    openai: {
      'gpt-4': 300,
      'gpt-3.5-turbo': 100
    },
    deepseek: {
      'deepseek-chat': 50
    }
  };

  return estimates[provider]?.[model] || 100; // Default $1.00 estimate
}