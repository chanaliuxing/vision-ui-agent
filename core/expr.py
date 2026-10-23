import ast, operator as op
from .context import Ctx

_ALLOWED = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Mod: op.mod, ast.Pow: op.pow,
    ast.Eq: op.eq, ast.NotEq: op.ne, ast.Lt: op.lt, ast.LtE: op.le, ast.Gt: op.gt, ast.GtE: op.ge,
    ast.And: lambda x,y: x and y, ast.Or: lambda x,y: x or y,
}

def resolve(v, ctx: Ctx):
    if isinstance(v, str) and v.startswith("@"):
        return ctx.vars[v[1:]]
    return v

def eval_expr(expr: str, ctx: Ctx):
    node = ast.parse(expr, mode="eval")
    def _eval(n):
        if isinstance(n, ast.Expression): return _eval(n.body)
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.Name): return ctx.vars[n.id]
        if isinstance(n, ast.Subscript):
            obj = _eval(n.value)
            key = _eval(n.slice)
            return obj[key]
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED:
            return _ALLOWED[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.BoolOp) and type(n.op) in _ALLOWED:
            values = [_eval(v) for v in n.values]
            result = values[0]
            for v in values[1:]:
                result = _ALLOWED[type(n.op)](result, v)
            return result
        if isinstance(n, ast.Compare):
            left = _eval(n.left)
            for opnode, comp in zip(n.ops, n.comparators):
                right = _eval(comp)
                if not _ALLOWED[type(opnode)](left, right): return False
                left = right
            return True
        raise ValueError("Disallowed expression")
    return _eval(node)