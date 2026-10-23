// src/index.js
import express from "express";
import cors from "cors";
import { auth } from "./auth.js";
import { devices } from "./devices.js";
import { llm } from "./llm.js";
import { adminKeys } from "./admin_keys.js";
import { billing } from "./billing.js";
import { webhooks } from "./webhooks.js";
import { marketplace } from "./marketplace.js";

const app = express();

app.use(cors());
app.use(express.json({ limit: "2mb" }));

app.get("/healthz", (req, res) => res.json({ ok: true }));
app.use("/auth", auth);
app.use("/devices", devices);
app.use("/llm", llm);
app.use("/admin", adminKeys);
app.use("/billing", billing);
app.use("/webhooks", webhooks);
app.use("/marketplace", marketplace);

// Error handling middleware
app.use((err, req, res, next) => {
  console.error("Unhandled error:", err);
  res.status(500).json({ error: "internal server error" });
});

const port = process.env.PORT || 8080;
app.listen(port, () => {
  console.log(`AutoAgent API server listening on port ${port}`);
});