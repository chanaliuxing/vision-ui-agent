import type { WorkflowDefinition, LintIssue } from '../types';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

// Load action IDs from registry
function loadActionIds(): string[] {
  try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    const registryPath = join(__dirname, '../../registry/index.json');
    const registryContent = readFileSync(registryPath, 'utf-8');
    const registryIndex = JSON.parse(registryContent);
    return registryIndex.actions.map((a: any) => a.id);
  } catch (error) {
    console.warn('Failed to load action registry:', error);
    return [];
  }
}

const ACTION_IDS = loadActionIds();

// 增强的自动修复功能
export function enhancedAutoFix(workflow: WorkflowDefinition, issues: LintIssue[]): {
  patched: WorkflowDefinition;
  patch: any[];
  notes: string[];
  appliedFixes: LintIssue[];
} {
  const w = JSON.parse(JSON.stringify(workflow)); // Deep clone
  const patch: any[] = [];
  const notes: string[] = [];
  const appliedFixes: LintIssue[] = [];

  // 处理现有的问题
  for (const issue of issues) {
    if (issue.fix && canAutoFix(issue.fix)) {
      try {
        applyFixToWorkflow(w, issue);
        appliedFixes.push(issue);
      } catch (error) {
        console.warn(`Failed to apply fix for ${issue.code}:`, error);
      }
    }
  }

  // 增强: 扫描未知动作并提供建议
  w.steps?.forEach((s: any, i: number) => {
    if (s.type === "action" && s.uses && !ACTION_IDS.includes(s.uses)) {
      const guess = nearestActionId(s.uses);
      if (guess) {
        notes.push(`step ${s.id}: unknown action "${s.uses}", did you mean "${guess}"?`);
      }
    }
  });

  // 增强: ext.click ref → x/y 落地
  w.steps?.forEach((s: any, i: number) => {
    if (s.uses === "ext.click") {
      const r = landClickRef(s.params);
      if (r.changed) {
        w.steps[i].params = r.params;
        patch.push({ op: "replace", path: `/steps/${i}/params`, value: r.params });
        notes.push(`step ${s.id}: resolved ref → x/y`);
      }
    }
  });

  // 增强: 检查缺失的 edges
  if (!w.edges || w.edges.length === 0) {
    if (w.steps && w.steps.length > 1) {
      const sequentialEdges = generateSequentialEdges(w.steps);
      w.edges = sequentialEdges;
      patch.push({ op: "add", path: "/edges", value: sequentialEdges });
      notes.push("added sequential edges between steps");
    }
  }

  return { patched: w, patch, notes, appliedFixes };
}

// F6: WF020 unknown action → 提示最相近动作（不直接替换，返回 notes）
function nearestActionId(bad: string): string | null {
  let best = "";
  let bestD = 1e9;
  for (const id of ACTION_IDS) {
    const d = levenshtein(bad, id);
    if (d < bestD) {
      bestD = d;
      best = id;
    }
  }
  return bestD <= Math.max(3, Math.floor(best.length * 0.34)) ? best : null;
}

// F7: 将 ext.click 的 params.ref（若是数组/对象）落地为 x/y
function landClickRef(params: any): { changed: boolean; params: any } {
  if (!params) return { changed: false, params };
  if ("ref" in params) {
    const ref = params.ref;
    if (Array.isArray(ref) && ref.length >= 2) {
      const [x, y] = ref;
      const p = { ...params };
      delete p.ref;
      p.x = x;
      p.y = y;
      return { changed: true, params: p };
    }
    if (ref && typeof ref === "object" && "x" in ref && "y" in ref) {
      const p = { ...params };
      delete p.ref;
      p.x = ref.x;
      p.y = ref.y;
      return { changed: true, params: p };
    }
  }
  return { changed: false, params };
}

function canAutoFix(fix: any): boolean {
  return fix.type === 'add' || fix.type === 'replace';
}

function applyFixToWorkflow(workflow: any, issue: LintIssue): void {
  const fix = issue.fix!;

  if (fix.type === 'add' && fix.target && fix.value !== undefined) {
    applyAddFix(workflow, fix.target, fix.value);
  } else if (fix.type === 'replace' && fix.target && fix.value !== undefined) {
    applyReplaceFix(workflow, fix.target, fix.value);
  }
}

function applyAddFix(workflow: any, target: string, value: any): void {
  const pathParts = target.split('/').filter(p => p !== '');
  let current: any = workflow;

  for (let i = 0; i < pathParts.length - 1; i++) {
    const part = pathParts[i];

    if (part === 'steps' && typeof pathParts[i + 1] === 'string' && !isNaN(parseInt(pathParts[i + 1]))) {
      const index = parseInt(pathParts[i + 1]);
      current = current.steps[index];
      i++;
    } else if (current[part] === undefined) {
      current[part] = {};
      current = current[part];
    } else {
      current = current[part];
    }
  }

  const finalKey = pathParts[pathParts.length - 1];
  current[finalKey] = value;
}

function applyReplaceFix(workflow: any, target: string, value: any): void {
  const pathParts = target.split('/').filter(p => p !== '');
  let current: any = workflow;

  for (let i = 0; i < pathParts.length - 1; i++) {
    const part = pathParts[i];

    if (part === 'steps' && typeof pathParts[i + 1] === 'string' && !isNaN(parseInt(pathParts[i + 1]))) {
      const index = parseInt(pathParts[i + 1]);
      current = current.steps[index];
      i++;
    } else {
      current = current[part];
    }
  }

  const finalKey = pathParts[pathParts.length - 1];
  current[finalKey] = value;
}

function generateSequentialEdges(steps: any[]): any[] {
  const edges = [];
  for (let i = 0; i < steps.length - 1; i++) {
    edges.push({
      from: steps[i].id,
      to: steps[i + 1].id
    });
  }
  return edges;
}

// 轻量 Levenshtein
function levenshtein(a: string, b: string): number {
  const m = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) m[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      m[i][j] = Math.min(
        m[i - 1][j] + 1,
        m[i][j - 1] + 1,
        m[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
    }
  }
  return m[a.length][b.length];
}