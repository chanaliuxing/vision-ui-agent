// server/src/payments/stripe.js
// Stripe payment provider implementation
import { pool } from "../db.js";

// Mock Stripe implementation for demo purposes
// In production, replace with: import Stripe from "stripe";

class MockStripe {
  constructor(secretKey, options) {
    this.secretKey = secretKey;
    this.options = options;
  }

  customers = {
    create: async ({ email, metadata }) => {
      return {
        id: `cus_mock_${Date.now()}`,
        email,
        metadata
      };
    }
  };

  checkout = {
    sessions: {
      create: async ({ mode, customer, line_items, success_url, cancel_url, payment_method_types }) => {
        const sessionId = `cs_mock_${Date.now()}`;
        return {
          id: sessionId,
          url: `https://checkout.stripe.com/mock/${sessionId}?success_url=${encodeURIComponent(success_url)}&cancel_url=${encodeURIComponent(cancel_url)}`
        };
      }
    }
  };

  billingPortal = {
    sessions: {
      create: async ({ customer, return_url }) => {
        return {
          url: `https://billing.stripe.com/p/session/mock_${customer}?return_url=${encodeURIComponent(return_url)}`
        };
      }
    }
  };

  webhooks = {
    constructEvent: (rawBody, signature, endpointSecret) => {
      // Mock webhook event construction
      return {
        id: `evt_mock_${Date.now()}`,
        type: "checkout.session.completed",
        data: {
          object: {
            id: "cs_mock_123",
            customer: "cus_mock_123",
            subscription: "sub_mock_123",
            metadata: {}
          }
        }
      };
    }
  };
}

const stripe = new MockStripe(process.env.STRIPE_SECRET_KEY || "sk_test_mock", {
  apiVersion: "2024-06-20"
});

export async function createCheckoutSession({ user, plan, mode = "subscription", success_url, cancel_url }) {
  // Get plan pricing
  const { rows: plans } = await pool.query(
    "select * from plan_products where key=$1",
    [plan]
  );

  if (!plans.length) {
    throw new Error(`Plan ${plan} not found`);
  }

  const planData = plans[0];
  const customer = await ensureCustomer(user);

  // Create checkout session
  const session = await stripe.checkout.sessions.create({
    mode,
    customer: customer.stripe_customer_id,
    line_items: [{
      price_data: {
        currency: 'usd',
        product_data: {
          name: planData.name,
          description: planData.description
        },
        unit_amount: Math.round(planData.monthly_price_usd * 100), // Convert to cents
        recurring: mode === 'subscription' ? { interval: 'month' } : undefined
      },
      quantity: 1
    }],
    success_url,
    cancel_url,
    payment_method_types: ["card"],
    metadata: {
      user_id: user.id,
      plan_key: plan
    }
  });

  return { id: session.id, url: session.url };
}

export async function createPortalSession({ user, return_url }) {
  const customer = await ensureCustomer(user);
  const portal = await stripe.billingPortal.sessions.create({
    customer: customer.stripe_customer_id,
    return_url
  });
  return { url: portal.url };
}

export function verifyWebhook(rawBody, sig) {
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET || "whsec_mock_secret";
  return stripe.webhooks.constructEvent(rawBody, sig, endpointSecret);
}

async function ensureCustomer(user) {
  // Check if user already has a Stripe customer ID
  if (user.stripe_customer_id) {
    return { stripe_customer_id: user.stripe_customer_id };
  }

  // Create new Stripe customer
  const customer = await stripe.customers.create({
    email: user.email,
    metadata: { user_id: user.id }
  });

  // Save customer ID to database
  await pool.query(
    "update users set stripe_customer_id=$1 where id=$2",
    [customer.id, user.id]
  );

  return { stripe_customer_id: customer.id };
}

// Token price calculation helper
export function tokensToCents(provider, model, promptTokens, completionTokens, currency = 'usd') {
  // Simplified pricing (in production, this would be more comprehensive)
  const pricing = {
    openai: {
      'gpt-4': { prompt: 0.003, completion: 0.006 },
      'gpt-3.5-turbo': { prompt: 0.0015, completion: 0.002 }
    },
    gemini: {
      'gemini-pro': { prompt: 0.001, completion: 0.002 }
    },
    deepseek: {
      'deepseek-chat': { prompt: 0.0005, completion: 0.001 }
    }
  };

  const rates = pricing[provider]?.[model] || { prompt: 0.001, completion: 0.002 };
  const totalCost = (promptTokens * rates.prompt + completionTokens * rates.completion) / 1000;

  return Math.round(totalCost * 100); // Convert to cents
}