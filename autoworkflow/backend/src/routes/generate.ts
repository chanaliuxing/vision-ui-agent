import { Router } from "express";
import { generateWorkflow } from "../services/generate.js";

export const generateRouter = Router();

/**
 * body: { type?: string, complexity?: "small"|"medium"|"large", description: string, allow_actions?: string[] }
 */
generateRouter.post("/generate", async (req, res) => {
  const body = req.body || {};
  if (!body.description) return res.status(400).json({ error: "description is required" });

  try {
    const result = await generateWorkflow(body);
    if (!result.ok) return res.status(400).json(result);
    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});