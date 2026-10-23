// server/src/payments/index.js
// Payment provider factory and unified exports

import * as StripePay from "./stripe.js";

export function getPaymentProvider(provider = "stripe") {
  switch (provider) {
    case "stripe":
      return StripePay;
    default:
      throw new Error(`Unsupported payment provider: ${provider}`);
  }
}

// Re-export Stripe as default
export const {
  createCheckoutSession,
  createPortalSession,
  verifyWebhook,
  tokensToCents
} = StripePay;