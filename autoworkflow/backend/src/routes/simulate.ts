import { Router } from "express";
import { createValidator } from "../lib/ajv.js";
import { simulateWorkflow } from "../sim/runner.js";

const router = Router();
const { validateWorkflow } = createValidator();

router.post("/simulate", async (req, res) => {
  const {
    workflow,
    seed,
    provider = "default",
    device = { width: 1440, height: 900, scale: 1, name: "web-1440x900" },
    replay_trace = [],
    fingerprint_index = {},
    explain = false
  } = req.body || {};

  if (!workflow) return res.status(400).json({ error: "missing 'workflow' in body" });

  const validationResult = validateWorkflow(workflow);
  if (!validationResult) {
    return res.status(400).json({
      error: "schema validation failed",
      issues: (validateWorkflow.errors || []).map(e => ({
        pointer: e.instancePath || "/",
        message: e.message
      }))
    });
  }

  try {
    const result = await simulateWorkflow(workflow, seed, {
      provider,
      device,
      replay_trace,
      fingerprint_index,
      explain
    });
    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});

export { router as simulateRouter };