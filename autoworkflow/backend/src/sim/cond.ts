import { readRef } from "./strings.js";

// 仅支持：
//   - 布尔常量 true/false
//   - 变量名：vars.x / outputs.step.y / globals.env.K
//   - expr == "text" / expr != "text"
//   - contains(expr, "needle")
export function evalCond(cond: string | undefined, ctx: Record<string, any>): boolean {
  if (!cond) return true;
  const s = cond.trim();

  if (s === "true") return true;
  if (s === "false") return false;

  // contains(a, "b")
  const mContains = /^contains\((.+?),\s*"(.*)"\)$/.exec(s);
  if (mContains) {
    const left = valueOf(mContains[1].trim(), ctx);
    return String(left).includes(mContains[2]);
  }

  // expr == "literal" | expr != "literal"
  const mEq = /^(.+?)(==|!=)\s*"(.*)"$/.exec(s);
  if (mEq) {
    const left = String(valueOf(mEq[1].trim(), ctx));
    const lit = mEq[3];
    return mEq[2] === "==" ? left === lit : left !== lit;
  }

  // 单变量真假
  const v = valueOf(s, ctx);
  return !!v;
}

function valueOf(expr: string, ctx: Record<string, any>): any {
  if (expr.startsWith("vars.") || expr.startsWith("outputs.") || expr.startsWith("globals.")) {
    return readRef(expr, ctx);
  }
  // 字面量 "abc"
  if ((expr.startsWith("\"") && expr.endsWith("\"")) || (expr.startsWith("'") && expr.endsWith("'"))) {
    return expr.slice(1, -1);
  }
  return expr; // 其他按字符串返回
}