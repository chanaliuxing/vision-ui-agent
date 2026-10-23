
# 需求速记（面向落地）

* 可插拔 **Action Engine**（变量/数据/控制流/异步/MQ/DB/LLM）
* **多工作流并行**，**高优先级抢占**（HP > LP），典型：WeChat 轮询（LP）+ 回复（HP）
* **异步解耦**：`llm.submit → llm.request → (云端路由+校验) → llm.complete → 设备HP队列`
* **登录/计费/授权**：机器识别码，多设备许可，工作流商店（下载/付费/授权），暂停/继续/停止
* **多模型+用户自带API Key**：按动作/工作流路由，云端强校验JSON Schema
* **云端/客户端分层**，可离线缓存，结构化日志与 artifacts，可回放/断点恢复（checkpoint）



详细落地方案：
阶段0，阶段1，

太好，直接开工。下面是**阶段 0** 和 **阶段 1** 的“可直接落地”方案：包含目录调整、关键代码骨架、演示用工作流、如何运行、验收标准与回退方案。按这两步做完，你就能立刻看到引擎版本/开关在日志里生效，以及**变量/循环/条件**驱动的可见点击流程跑起来。

---

# 阶段 0｜基线冻结 & 开关（不改变现有行为，但把“可进化”的骨架装上）

## 0.1 目标

* 固定一个引擎版本号（便于排障与兼容判断）。
* 增加**特性开关**（feature flags），后续新能力按开关启用/关闭。
* 统一**artifacts** 目录与结构化日志格式，不改变现有功能。

## 0.2 目录与文件（新增/改动）

```
repo/
├─ core/
│  ├─ __init__.py              # 版本号、对外常量
│  ├─ flags.py                 # 读取/合并 feature flags
│  ├─ logging_setup.py         # 结构化日志配置
│  └─ artifacts.py             # 产物快照目录 & 帮助函数
├─ config/
│  ├─ feature_flags.default.json
│  └─ settings.example.yaml
├─ examples/
│  └─ demo_baseline.json       # 演示用最小工作流（不改变现有逻辑）
├─ run_workflow.py             # 入口脚本（已存在：轻改接入 flags 与日志）
```

### `core/__init__.py`

```python
ENGINE_VERSION = "0.4.0"
```

### `config/feature_flags.default.json`

```json
{
  "async_engine": false,
  "hp_lp_scheduler": false,
  "mq_rabbit": false,
  "auth_billing": false,
  "marketplace": false,
  "checkpoints": false,
  "strict_schema_llm": false
}
```

### `core/flags.py`

```python
import json, os
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "feature_flags.default.json"

def load_flags(override_path: str | None = None) -> dict:
    with open(DEFAULT, "r", encoding="utf-8") as f:
        flags = json.load(f)
    if override_path and os.path.exists(override_path):
        with open(override_path, "r", encoding="utf-8") as f:
            user = json.load(f)
        flags.update(user)
    # 支持环境变量覆盖（FLAG_async_engine=true）
    for k in list(flags.keys()):
        env = os.getenv(f"FLAG_{k}")
        if env is not None:
            flags[k] = env.lower() in ("1","true","yes","on")
    return flags
```

### `core/logging_setup.py`

```python
import logging, sys
from . import ENGINE_VERSION

def setup_logger():
    logger = logging.getLogger("auto")
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        fmt="%(asctime)s | v=%(engine)s | lvl=%(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    h.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(h)
    # 统一 extra
    class VersionAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.setdefault("extra", {})
            extra.setdefault("engine", ENGINE_VERSION)
            return msg, kwargs
    return VersionAdapter(logger, {})
```

### `core/artifacts.py`

```python
from pathlib import Path
import shutil, json, time

def run_dir(base: str, run_id: str) -> Path:
    p = Path(base) / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def step_dir(base: str, run_id: str, state: str, step_idx: int) -> Path:
    p = run_dir(base, run_id) / f"{state}_step{step_idx:03d}"
    p.mkdir(parents=True, exist_ok=True)
    return p

def dump_json(p: Path, name: str, obj):
    with open(p / name, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def snapshot_note(p: Path, note: str):
    with open(p / "README.txt", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + note + "\n")
```

### 轻改 `run_workflow.py`（示意）

```python
# from core import ENGINE_VERSION
# from core.flags import load_flags
# from core.logging_setup import setup_logger
# from core.artifacts import run_dir

# 读取 --flags path，可选
# logger.info(f"engine boot", extra={"engine": ENGINE_VERSION, "flags": flags})

# 执行前创建 artifacts/<run_id>，执行后写入 summary.json
```

### `examples/demo_baseline.json`（可选）

保留你现有的 demo 工作流（此处仅作为“能跑通”的烟测）。

## 0.3 如何运行 & 预期输出

```
python run_workflow.py --workflow examples/demo_baseline.json --flags my_flags.json
```

预期日志关键行（示例）：

```
21:12:10 | v=0.4.0 | lvl=INFO | engine boot flags={'async_engine': False, ...}
21:12:10 | v=0.4.0 | lvl=INFO | artifacts=artifacts/2025-09-15T211210Z-<run_id>
```

`artifacts/<run_id>/README.txt` 存在。

## 0.4 验收标准

* 不改动原有动作/行为即可跑通。
* 日志首行出现 `v=0.4.0` 与 flags 列表。
* `artifacts/<run_id>/` 目录按执行生成。

## 0.5 回退方案

* 通过 `--flags` 或环境变量把所有新 flag 置为 `false` 即可回到旧行为。
* 代码完全向后兼容；新增文件不被引用也不影响运行。

---

# 阶段 1｜Action Engine 基座（变量/数据/控制流 + DOM/坐标点击）

> 做完此阶段，你可以**用 JSON 语言写“微脚本”**：`set_variable / get_list_item / branch / click_coordinates / ext.extract / wait_until / scroll_until`，跑一个可见的“循环打开每个条目→返回”的小流程。

## 1.1 目标

* 实现**可插拔动作注册**、**变量系统**、**安全表达式**、**同步 Runner** 与**首批动作**。
* 提供一个**可运行 demo 工作流**，看见“循环 + 条目点击”效果。

## 1.2 目录与文件（新增/改动）

```
core/
├─ registry.py        # 动作注册与获取
├─ context.py         # 上下文/服务适配器
├─ expr.py            # @变量解引用 & 安全表达式
└─ runner.py          # 同步状态机执行器（阶段1先同步）
actions/
├─ vars.py            # set_variable / increment_variable / get_list_length / get_list_item / query_data
├─ flow.py            # branch
├─ wait_scroll.py     # wait_until / scroll_until
├─ exec.py            # click_coordinates
└─ ext.py             # ext.open_url / ext.extract / ext.go_back / ext.exists / ext.click(optional)
examples/
└─ demo_loop_posts.json
```

### `core/registry.py`

```python
from typing import Callable, Dict
_ACTIONS: Dict[str, Callable] = {}

def register_action(name: str):
    def deco(fn: Callable):
        _ACTIONS[name] = fn
        return fn
    return deco

def get_action(name: str) -> Callable:
    if name not in _ACTIONS:
        raise KeyError(f"Action '{name}' not registered")
    return _ACTIONS[name]
```

### `core/context.py`

```python
from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class Services:
    dom: Any     # 提供 open/exists/extract/go_back/click 等
    os: Any      # 提供 move_to/click/scroll
    vision: Any  # 预留
    logger: Any

@dataclass
class Ctx:
    vars: Dict[str, Any] = field(default_factory=dict)
    last_result: Any = None
    services: Services = None
    run_id: str = "dev"
    artifacts_dir: str = "artifacts"
```

### `core/expr.py`

```python
import ast, operator as op
from .context import Ctx

_ALLOWED = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Mod: op.mod, ast.Pow: op.pow,
    ast.Eq: op.eq, ast.NotEq: op.ne, ast.Lt: op.lt, ast.LtE: op.le, ast.Gt: op.gt, ast.GtE: op.ge,
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
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED:
            return _ALLOWED[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.Compare):
            left = _eval(n.left)
            for opnode, comp in zip(n.ops, n.comparators):
                right = _eval(comp)
                if not _ALLOWED[type(opnode)](left, right): return False
                left = right
            return True
        raise ValueError("Disallowed expression")
    return _eval(node)
```

### `core/runner.py`

```python
import time
from typing import Dict, Any, List
from .registry import get_action
from .expr import eval_expr
from .artifacts import step_dir, dump_json

class WorkflowRunner:
    def __init__(self, spec: Dict[str, Any], ctx):
        self.spec = spec
        self.ctx = ctx
        self.state = spec["start"]
        self.ctx.vars.update(spec.get("vars", {}))
        self.step_idx = 0

    def run(self):
        states = self.spec["states"]
        while self.state:
            st = states[self.state]
            self._run_state(st)
            self.state = self._next_state(st)

    def _run_state(self, st: Dict[str, Any]):
        actions: List[Dict[str, Any]] = st.get("actions", [])
        for step in actions:
            self.step_idx += 1
            self._run_action(step)

    def _run_action(self, step: Dict[str, Any]):
        fn = get_action(step["do"])
        t0 = time.time()
        res = fn(step, self.ctx)  # 同步执行
        if step.get("save"): self.ctx.vars[step["save"]] = res
        d = step_dir(self.ctx.artifacts_dir, self.ctx.run_id, self.state, self.step_idx)
        dump_json(d, "action.json", {"do": step["do"], "params": {k:v for k,v in step.items() if k!='do'}})
        dump_json(d, "result.json", res if isinstance(res, (dict, list)) else {"result": str(res)})
        self.ctx.services.logger.info(
            f"action={step['do']} dur_ms={int((time.time()-t0)*1000)}"
        )

    def _next_state(self, st: Dict[str, Any]):
        # transitions: [{if, go_to}] 或 [{go_to}]
        for tr in st.get("transitions", []):
            cond = tr.get("if")
            if cond is None or eval_expr(cond, self.ctx):
                return tr.get("go_to")
        return None
```

### `actions/vars.py`

```python
from core.registry import register_action
from core.expr import resolve

@register_action("set_variable")
def set_variable(step, ctx, **_):
    ctx.vars[step["name"]] = resolve(step.get("value"), ctx)
    return {"ok": True, "value": ctx.vars[step["name"]]}

@register_action("increment_variable")
def increment_variable(step, ctx, **_):
    ctx.vars[step["name"]] = ctx.vars.get(step["name"], 0) + 1
    return {"ok": True, "value": ctx.vars[step["name"]]}

@register_action("get_list_length")
def get_list_length(step, ctx, **_):
    data = resolve(step["from"], ctx) or []
    return len(data)

@register_action("get_list_item")
def get_list_item(step, ctx, **_):
    data = resolve(step["from"], ctx) or []
    idx = resolve(step["index"], ctx)
    return data[idx]

@register_action("query_data")
def query_data(step, ctx, **_):
    obj = resolve(step["from"], ctx)
    path = step.get("query","")
    cur = obj
    for part in path.split("."):
        if part:
            cur = cur[part] if isinstance(cur, dict) else getattr(cur, part)
    return cur
```

### `actions/flow.py`

```python
from core.registry import register_action
from core.expr import eval_expr

@register_action("branch")
def branch(step, ctx, **_):
    cond = step["if"]
    v = eval_expr(cond, ctx)
    # 返回一个提示：runner 不强制跳转，这里仅给调试信息
    return {"ok": True, "cond": cond, "value": v, "then": step.get("then"), "else": step.get("else")}
```

### `actions/wait_scroll.py`

```python
from core.registry import register_action
import time

@register_action("wait_until")
def wait_until(step, ctx, **_):
    chk = step["check"]; timeout = step.get("timeout_ms", 8000)/1000; poll = step.get("poll_ms", 300)/1000
    t0 = time.time()
    while time.time()-t0 < timeout:
        if chk["type"] == "dom" and ctx.services.dom.exists(chk["selector"]):
            return {"ok": True}
        time.sleep(poll)
    raise TimeoutError("wait_until timeout")

@register_action("scroll_until")
def scroll_until(step, ctx, **_):
    anchor = step["anchor"]; max_sc = step.get("max_scrolls", 30); step_px = step.get("step_px", 800)
    for _ in range(max_sc):
        if anchor["type"]=="dom" and ctx.services.dom.exists(anchor["selector"]):
            return {"ok": True}
        ctx.services.os.scroll(step_px)
    raise TimeoutError("scroll_until anchor not reached")
```

### `actions/exec.py`

```python
from core.registry import register_action
from core.expr import resolve

@register_action("click_coordinates")
def click_coordinates(step, ctx, **_):
    bbox = resolve(step["bbox"], ctx)  # {x,y,w,h}
    x = int(bbox["x"] + bbox["w"]/2)
    y = int(bbox["y"] + bbox["h"]/2)
    ctx.services.os.move_to(x, y)
    ctx.services.os.click()
    return {"ok": True, "x": x, "y": y}
```

### `actions/ext.py`（桥接你的 MV3 扩展；暂时提供一个“模拟器”便于本机自测）

```python
from core.registry import register_action

@register_action("ext.open_url")
def ext_open_url(step, ctx, **_):
    return ctx.services.dom.open(step["url"])

@register_action("ext.exists")
def ext_exists(step, ctx, **_):
    sel = step["selector"]
    return {"exists": ctx.services.dom.exists(sel)}

@register_action("ext.extract")
def ext_extract(step, ctx, **_):
    return ctx.services.dom.extract(step.get("query", {}))

@register_action("ext.go_back")
def ext_go_back(step, ctx, **_):
    return ctx.services.dom.go_back()
```

> **DomAdapter 最小协议（你已有扩展）**
>
> * `open(url)` → {"ok": True}
> * `exists(selector)` → bool
> * `extract(query: dict)` → dict（例如返回 `{"posts":[{"bbox":{"x":..},"title":".."}]}`）
> * `go_back()` → {"ok": True}

为方便没有浏览器联调时自测，建议做个**模拟 DomAdapter**（本地返回固定 posts 列表），跑通控制流与坐标点击（OS 层可先打印坐标）。等联调时用真正的适配器替换。

### 演示工作流 `examples/demo_loop_posts.json`

```json
{
  "name": "Demo Loop Posts",
  "start": "open_and_extract",
  "vars": { "idx": 0 },
  "states": {
    "open_and_extract": {
      "actions": [
        { "do": "ext.open_url", "url": "https://example.com/list" },
        { "do": "wait_until", "check": { "type": "dom", "selector": ".post-item" }, "timeout_ms": 5000 },
        { "do": "ext.extract", "query": { "posts": "CSS:.post-item" }, "save": "posts" },
        { "do": "get_list_length", "from": "@posts", "save": "total" }
      ],
      "transitions": [{ "go_to": "loop" }]
    },
    "loop": {
      "actions": [
        { "do": "branch", "if": "@idx >= @total", "then": "done", "else": "open_post" }
      ],
      "transitions": [
        { "if": "@idx >= @total", "go_to": "done" },
        { "go_to": "open_post" }
      ]
    },
    "open_post": {
      "actions": [
        { "do": "get_list_item", "from": "@posts", "index": "@idx", "save": "cur" },
        { "do": "query_data", "from": "@cur", "query": "bbox", "save": "bbox" },
        { "do": "click_coordinates", "bbox": "@bbox" },
        { "do": "wait_until", "check": { "type": "dom", "selector": ".detail" }, "timeout_ms": 4000 },
        { "do": "ext.go_back" },
        { "do": "increment_variable", "name": "idx" }
      ],
      "transitions": [{ "go_to": "loop" }]
    },
    "done": { "actions": [] }
  }
}
```

## 1.3 如何运行（最小自测）

1. 日志初始化（阶段 0 已完成）：

```
export FLAG_async_engine=false
python run_workflow.py --workflow examples/demo_loop_posts.json
```

2. 如果尚未接MV3，临时把 `Services.dom` 设成模拟器（返回三条 posts 的 bbox），把 `Services.os.click()` 实现为打印坐标（或调用 `pyautogui.moveTo` 看光标移动）。

**预期日志**

```
.. | v=0.4.0 | INFO | action=ext.open_url dur_ms=...
.. | v=0.4.0 | INFO | action=wait_until dur_ms=...
.. | v=0.4.0 | INFO | action=ext.extract dur_ms=...   # artifacts/..../result.json 有 posts 数组
.. | v=0.4.0 | INFO | action=get_list_length dur_ms=...
.. | v=0.4.0 | INFO | action=get_list_item dur_ms=...
.. | v=0.4.0 | INFO | action=click_coordinates dur_ms=...  # 光标移动/点击可见
...
```

**预期产物**

* `artifacts/<run_id>/open_post_step00X/action.json` 与 `result.json` 记下每一步输入/输出；
* 如接了真实 DOM 适配器，能看到页面来回切换。

## 1.4 成功标准（阶段 1）

* **用 JSON 控制变量/条件/循环**，可见点击每个条目并返回。
* 日志/产物清晰记录每步输入/输出。
* 不依赖后续功能（MQ/LLM/优先级）也能稳定跑完。

## 1.5 风险与兜底

* 如果 DOM 适配器暂时未接：用**模拟适配器**自测逻辑，后面再替换。
* OS 点击在多显示器/缩放下偏移：先观测打印坐标，确认后再启用真实点击。
* 循环过快导致反自动化：阶段 1 先不加随机延迟；阶段 11 会统一加节流与 jitter。

阶段2:
直接上**阶段 2｜本地抢占式调度（无 MQ，仅内存队列）**的落地包。目标是：不改你现有浏览器/视觉通道，不上 Rabbit/SQS，也能看到**High-Priority（HP）打断 Low-Priority（LP）** 的效果，并把这套“可抢占点”的引擎骨架稳定下来。做完这个阶段，你能同时跑两个工作流：

* LP：模拟 WeChat 轮询（每几秒发现“红点”就产生一条任务）；
* HP：收到 LP 产生的任务后**立即抢占**，优先执行“回复”。

---

# 阶段 2：落地目标

* 新增**本地内存总线**（LocalBus）模拟 MQ 的 `publish/consume`。
* 新增**抢占式调度器 Scheduler**（基于 `asyncio`），LP 每步后检查是否有 HP 待处理，立刻让渡。
* 在不依赖真实 LLM/MQ 的前提下，端到端跑出“LP 轮询 → 触发 HP → HP 抢占执行”的可见日志流。
* 保持阶段 1 的 **WorkflowRunner** 可复用，仅新增一个 **异步 step 接口** 实现“执行一小步就让出”的能力。

---

## 2.1 目录与文件（新增/改动）

```
repo/
├─ core/
│  ├─ runner.py               # （轻改）新增 async step() 可一步步执行
│  └─ context.py              # Services 增加 mq（本地总线适配器）
├─ client/
│  ├─ scheduler.py            # 新：HP/LP 调度器（asyncio）
│  ├─ bus_local.py            # 新：本地内存总线（topic → asyncio.Queue）
│  └─ services_local.py       # 新：把 LocalBus 挂到 Services.mq
├─ actions/
│  ├─ mq_local.py             # 新：mq.publish / mq.consume（基于 LocalBus）
│  └─ demo.py                 # 新：demo.fake_red_dot（用于触发 HP）
└─ examples/
   ├─ stage2_lp_poller.json   # LP 工作流（轮询→发现→publish HP）
   └─ stage2_hp_responder.json# HP 工作流（consume→“响应”）
```

---

## 2.2 代码改动与新增

### 2.2.1 `core/context.py`（给 Services 增加 mq）

```python
from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class Services:
    dom: Any
    os: Any
    vision: Any
    mq: Any        # ★ 新增：消息总线（阶段2本地，阶段3换成 Rabbit/SQS）
    logger: Any

@dataclass
class Ctx:
    vars: Dict[str, Any] = field(default_factory=dict)
    last_result: Any = None
    services: Services = None
    run_id: str = "dev"
    artifacts_dir: str = "artifacts"
```

### 2.2.2 `core/runner.py`（在阶段1的基础上，增加 async step）

> 保留原来的 `run()`，但**不再在阶段2里调用**；改为用 `await runner.step(should_preempt)` 单步执行，支持在每个动作后**让出**调度。

```python
import time, asyncio
from typing import Dict, Any, List
from .registry import get_action
from .expr import eval_expr
from .artifacts import step_dir, dump_json

class WorkflowRunner:
    def __init__(self, spec: Dict[str, Any], ctx):
        self.spec = spec
        self.ctx = ctx
        self.state = spec["start"]
        self.ctx.vars.update(spec.get("vars", {}))
        self.step_idx = 0
        self.priority = spec.get("meta", {}).get("priority", "LOW")  # 'HIGH' | 'LOW'

    async def step(self, should_preempt):
        """执行当前 state 的所有 actions（每个动作后检查抢占点），然后根据 transitions 迁移到下一个 state。
           如果 should_preempt() 为 True，则提前让出（下次再继续当前 state 的剩余动作）。"""
        if not self.state:
            return
        st = self.spec["states"][self.state]
        actions: List[Dict[str, Any]] = st.get("actions", [])
        i = 0
        while i < len(actions):
            step = actions[i]
            await self._run_action_async(step)
            i += 1
            # 抢占点：每个动作后检查
            if await should_preempt():
                return
        # 动作执行完，才进行 transitions
        self.state = self._next_state(st)

    async def _run_action_async(self, step: Dict[str, Any]):
        fn = get_action(step["do"])
        t0 = time.time()
        # 动作本身是同步函数：在这里直接调用（若后续需要IO，可改为await fn(...)）
        res = fn(step, self.ctx)
        if step.get("save"): self.ctx.vars[step["save"]] = res
        d = step_dir(self.ctx.artifacts_dir, self.ctx.run_id, self.state, self.step_idx)
        dump_json(d, "action.json", {"do": step["do"], "params": {k:v for k,v in step.items() if k!='do'}})
        dump_json(d, "result.json", res if isinstance(res, (dict, list)) else {"result": str(res)})
        self.step_idx += 1
        self.ctx.services.logger.info(
            f"action={step['do']} dur_ms={int((time.time()-t0)*1000)} priority={self.priority}"
        )
        # 给事件循环一个机会调度（避免长时间占用）
        await asyncio.sleep(0)

    def _next_state(self, st: Dict[str, Any]):
        for tr in st.get("transitions", []):
            cond = tr.get("if")
            if cond is None or eval_expr(cond, self.ctx):
                return tr.get("go_to")
        return None
```

### 2.2.3 `client/bus_local.py`（本地内存总线）

```python
import asyncio
from typing import Dict

class LocalBus:
    def __init__(self):
        self._topics: Dict[str, asyncio.Queue] = {}

    def topic(self, name: str) -> asyncio.Queue:
        if name not in self._topics:
            self._topics[name] = asyncio.Queue()
        return self._topics[name]

    async def publish(self, topic: str, message):
        await self.topic(topic).put(message)

    async def consume(self, topic: str, timeout_ms: int | None = None):
        q = self.topic(topic)
        if timeout_ms is None:
            return await q.get()
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout_ms/1000)
        except asyncio.TimeoutError:
            return None

    def qsize(self, topic: str) -> int:
        return self.topic(topic).qsize()
```

### 2.2.4 `client/services_local.py`（把 LocalBus 接到 Services.mq）

```python
from core.context import Services
from .bus_local import LocalBus

class LocalMQAdapter:
    def __init__(self, bus: LocalBus):
        self.bus = bus
    async def publish(self, topic: str, message):
        await self.bus.publish(topic, message)
    async def consume(self, topic: str, timeout_ms: int | None = None):
        return await self.bus.consume(topic, timeout_ms)
    def qsize(self, topic: str) -> int:
        return self.bus.qsize(topic)

def build_services(dom, os, vision, logger, bus: LocalBus) -> Services:
    return Services(dom=dom, os=os, vision=vision, mq=LocalMQAdapter(bus), logger=logger)
```

### 2.2.5 `actions/mq_local.py`（动作：publish/consume）

> 注意：我们的 Runner 是 async，但动作仍是**同步函数**。为保持简单，这里把真正的 await 委托给一个**环形缓冲区**，由 Scheduler 预先灌入/取出。为了更“直觉”，我们在 **动作内部**使用 `asyncio.get_event_loop().create_task(...)` 启动协程，并把结果存在 `ctx.vars`（动作同步返回“已安排”）。这种做法在真实 MQ（阶段3）会改为纯同步投递（publish）和**阻塞式** `consume` 由 HP Runner 自己 await。

**更简单的实现（推荐本阶段）**：

* `mq.publish`：同步调用 `asyncio.create_task(services.mq.publish(...))`，立刻返回。
* `mq.consume`：**非阻塞**版本，带 `max_wait_ms`: 轮询 bus.qsize()，没消息就返回 `None`，交给 HP 工作流下个 step 再来拿（这样就不会阻塞一个动作，利于抢占）。

```python
import asyncio
from core.registry import register_action

@register_action("mq.publish")
def mq_publish(step, ctx, **_):
    topic = step["topic"]; payload = step.get("payload", {})
    loop = asyncio.get_event_loop()
    loop.create_task(ctx.services.mq.publish(topic, payload))
    return {"ok": True, "enqueued": True, "topic": topic}

@register_action("mq.consume")
def mq_consume(step, ctx, **_):
    topic = step["topic"]
    # 非阻塞消费：如果没有消息，返回 None，让工作流下次 step 再试
    if ctx.services.mq.qsize(topic) == 0:
        return {"msg": None}
    # 有消息则安排一个小协程把它取出来并塞到 ctx 里，然后返回“即将可用”
    async def _get_and_store():
        msg = await ctx.services.mq.consume(topic, timeout_ms=1)
        ctx.vars[step.get("save", "msg")] = msg
    asyncio.get_event_loop().create_task(_get_and_store())
    return {"msg": "pending"}
```

> 说明：我们这里用“**拉取-再检查**”的方式避免动作层阻塞。HP 工作流每一 step 都会 `mq.consume` 尝试拿消息，只要到达，就在下一步（或下两步）可见。

### 2.2.6 `actions/demo.py`（用于 LP 流模拟“发现红点”）

```python
from core.registry import register_action

@register_action("demo.fake_red_dot")
def fake_red_dot(step, ctx, **_):
    # 简单：每次调用把计数 +1，偶数次返回 has_red=True
    tick = ctx.vars.get("tick", 0) + 1
    ctx.vars["tick"] = tick
    return {"has_red": (tick % 2 == 0)}
```

---

## 2.3 调度器 `client/scheduler.py`

```python
import asyncio
from typing import Dict
from core.runner import WorkflowRunner

class Scheduler:
    def __init__(self, hp_runner: WorkflowRunner, lp_runners: Dict[str, WorkflowRunner], services):
        self.hp_runner = hp_runner
        self.lp_runners = lp_runners
        self.services = services

    async def start(self):
        await asyncio.gather(self._loop_hp(), self._loop_lp())

    async def _loop_hp(self):
        # HP 工作流：不停单步推进（每步很快），动作内部非阻塞地尝试 mq.consume
        while True:
            async def no_preempt(): return False
            await self.hp_runner.step(lambda: asyncio.sleep(0) or False)  # HP 不被抢占
            await asyncio.sleep(0)  # 把时间片让出去

    async def _loop_lp(self):
        while True:
            # round-robin 所有 LP 工作流，每个只执行一小步
            for wid, runner in self.lp_runners.items():
                async def should_preempt():
                    # ★ 抢占条件：HP 主题上有未处理消息，则立即让渡
                    return self.services.mq.qsize("hp") > 0
                await runner.step(should_preempt)
                # 如果出现 HP 消息，让出时间片给 HP
                if self.services.mq.qsize("hp") > 0:
                    await asyncio.sleep(0)
            # 避免忙等
            await asyncio.sleep(0.01)
```

> 说明：
>
> * 我们把 HP 主题名固定为 `"hp"`（只是本阶段的约定，阶段3会细分 topic）。
> * LP 每个动作后都会 `should_preempt()`；只要 `hp` 有消息，就**立即 return**，把控制权交回事件循环，HP 协程就能拿到调度运行。
> * HP 自身不会被抢占（你可以改造为也可被“更高优先级”抢占，当前不需要）。

---

## 2.4 示例工作流（可运行）

### 2.4.1 LP 轮询：`examples/stage2_lp_poller.json`

```json
{
  "name": "LP Poller",
  "meta": { "priority": "LOW" },
  "start": "poll",
  "vars": { "tick": 0 },
  "states": {
    "poll": {
      "actions": [
        { "do": "demo.fake_red_dot", "save": "rd" },
        { "do": "branch", "if": "@rd['has_red'] == True", "then": "publish_hp", "else": "sleep" }
      ],
      "transitions": [
        { "if": "@rd['has_red'] == True", "go_to": "publish_hp" },
        { "go_to": "sleep" }
      ]
    },
    "sleep": {
      "actions": [
        { "do": "set_variable", "name": "tmp", "value": 0 }  // 仅占一步，示范 LP 在“无事可做”时也会被抢占
      ],
      "transitions": [ { "go_to": "poll" } ]
    },
    "publish_hp": {
      "actions": [
        { "do": "mq.publish", "topic": "hp", "payload": { "contact": "Alice", "text": "新消息..." } }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

### 2.4.2 HP 响应：`examples/stage2_hp_responder.json`

```json
{
  "name": "HP Responder",
  "meta": { "priority": "HIGH" },
  "start": "wait",
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "hp", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None and @msg != 'pending' and @msg.get('payload') != None", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "set_variable", "name": "last_contact", "value": "@msg['payload']['contact']" },
        { "do": "set_variable", "name": "last_text", "value": "@msg['payload']['text']" }
        // 真正到阶段5再替换为 ext.focus_contact/os.type_and_send
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

> 说明：
>
> * `mq.consume` 在本阶段是“非阻塞尝试”。当 `msg == None` 或 `"pending"` 时，说明当前这一步尚未拿到实物；下一步又会回到 `wait` 再试，很快就能拿到。
> * 一旦 LP 发布了消息，HP 的下一次 `step()` 就会把它拿到，并跳到 `send`。

---

## 2.5 如何运行（最小自测）

你已有阶段 0/1 的基础。现在再加下面这段“main 启动器”（自写一个 `scripts/run_stage2_demo.py`）：

```python
# scripts/run_stage2_demo.py
import asyncio, uuid
from core.logging_setup import setup_logger
from core.context import Ctx
from core.runner import WorkflowRunner
from client.bus_local import LocalBus
from client.services_local import build_services
from client.scheduler import Scheduler

# 你已有的适配器，这里先做最小 stub
class DummyDOM: 
    def open(self, url): return {"ok": True}
    def exists(self, selector): return True
    def extract(self, query): return {"posts": []}
    def go_back(self): return {"ok": True}
class DummyOS:
    def move_to(self, x, y): pass
    def click(self): pass
    def scroll(self, px): pass
class DummyVision: pass

import json, pathlib
def load_spec(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

async def main():
    logger = setup_logger()
    bus = LocalBus()
    services = build_services(DummyDOM(), DummyOS(), DummyVision(), logger, bus)

    # LP runner
    lp_spec = load_spec("examples/stage2_lp_poller.json")
    lp_ctx = Ctx(services=services, run_id=str(uuid.uuid4()))
    lp_runner = WorkflowRunner(lp_spec, lp_ctx)

    # HP runner
    hp_spec = load_spec("examples/stage2_hp_responder.json")
    hp_ctx = Ctx(services=services, run_id=str(uuid.uuid4()))
    hp_runner = WorkflowRunner(hp_spec, hp_ctx)

    sched = Scheduler(hp_runner=hp_runner, lp_runners={"poller": lp_runner}, services=services)
    await sched.start()

if __name__ == "__main__":
    asyncio.run(main())
```

**运行：**

```
python scripts/run_stage2_demo.py
```

**预期日志（示例）**：

```
.. | v=0.4.0 | INFO | action=demo.fake_red_dot dur_ms=... priority=LOW
.. | v=0.4.0 | INFO | action=set_variable dur_ms=... priority=LOW
.. | v=0.4.0 | INFO | action=demo.fake_red_dot dur_ms=... priority=LOW
.. | v=0.4.0 | INFO | action=mq.publish dur_ms=... priority=LOW
.. | v=0.4.0 | INFO | action=mq.consume dur_ms=... priority=HIGH
.. | v=0.4.0 | INFO | action=set_variable dur_ms=... priority=HIGH   # last_contact=Alice
```

观察到：**一旦 LP 发布了 HP 消息，HP 立刻拿到时间片执行**；LP 继续在队尾等。

artifacts 目录下，每个 runner 都会生成自己的 `run_id` 子目录，step 日志可对照。

---

## 2.6 成功标准

* 同时运行 LP 与 HP；LP 周期性地产生“任务”，HP 几乎**立即**取到并执行。
* 在日志中，可以看到 LP 的动作序列被“插入”的 HP 动作打断（HP 的日志条目穿插出现）。
* 没有真实 MQ/LLM，也能稳定运行，且**无死锁**、**无阻塞**。

---

## 2.7 常见问题与兜底

* **HP 为什么没抢占？**
  检查 `Scheduler._loop_lp` 里的 `should_preempt()` 是否检测的是正确的 topic（本阶段 `"hp"`），以及 LP 的 step 是否每个动作后都调用了该回调（上面的实现是的）。

* **HP 拿不到消息 / `pending` 一直存在？**
  本阶段的 `mq.consume` 是“非阻塞尝试”。如果你想更紧凑，可以把 `mq.consume` 改成：当检测到有消息时，**直接同步从队列取出**并返回（不走 create\_task）；这会更快拿到数据，但要确保动作不阻塞。

* **CPU 占用高**
  调整 `Scheduler._loop_lp` 最后一行的 `await asyncio.sleep(0.01)`，或在 LP 的轮询工作流里加 `wait_ms` 动作（后面阶段会提供统一的节流/jitter）。

* **如何对接真实 DOM/WeChat**
  本阶段只打通调度逻辑；`DummyDOM/DummyOS` 随时可以替换成你已有的 MV3/pyautogui 适配器。HP 的“send”状态到阶段 5 会替换为真实 `ext.focus_contact_by_anchor_name` + `os.type_and_send`。

---

## 2.8 与后续阶段的衔接

* **阶段 3**：把 `client/bus_local.py` 替换为 Rabbit/SQS 适配（接口同名：`publish/consume/qsize`），`actions/mq_local.py` 改名 `actions/mq.py` 即可。
* **阶段 4**：HP 主题不再由 LP 直接发布，而是 LP → `llm.submit` → 云端回环 → 投递 `llm.complete` 到 HP topic。
* **阶段 5**：把 `send` 状态换成真实的 WeChat UI 动作，并引入 `resource_lock=WECHAT_UI`。

---

如果你已经把阶段 0/1 合进仓库，照着这个阶段 2 的文件加上去就能跑。跑完你会直观看到“**HP 抢占 LP**”的效果。

阶段3:
# 阶段 3｜消息队列切换到 SQS（本地：LocalStack；线上：真 AWS）

## 3.1 目标

* 用 **SQS** 取代阶段 2 的 LocalBus：实现 `publish / consume / qsize`，保证**HP 优先**。
* 使用 **FIFO 队列**（`*.fifo`）来获得稳定顺序与幂等（可选内容去重）。
* **保持现有工作流与调度器不变**（只替换 MQ 适配器）。
* 通过 **LocalStack** 在本地起环境，跑通“LP 轮询→发布 HP 消息→HP 抢占执行”。

---

## 3.2 基础设施（docker-compose + 环境变量）

### `docker-compose.sqs.yml`

```yaml
version: "3.9"
services:
  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"       # main edge port
      - "4571:4571"
    environment:
      - SERVICES=sqs
      - DEBUG=1
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - "./.localstack:/var/lib/localstack"
```

### `.env.example`

```
AWS_REGION=us-east-1
# 本地 LocalStack
AWS_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
# 生产切换：把 AWS_ENDPOINT_URL 去掉（或留空），并注入真实 AK/SK 或角色
```

启动：

```
docker compose -f docker-compose.sqs.yml up -d
```

---

## 3.3 初始化队列（创建 FIFO 队列 + 属性）

> SQS 不直接支持“队列长度精确查询”，但提供近似值 `ApproximateNumberOfMessages`。
> 我们用 **两条 FIFO 队列** 表示优先级： `device.<id>.hp.fifo` / `device.<id>.lp.fifo`。
> 阶段 3 先用一个 demo 设备 ID：`device.demo`.

### `scripts/bootstrap_sqs.py`

```python
import os, json
import boto3

region = os.getenv("AWS_REGION", "us-east-1")
endpoint = os.getenv("AWS_ENDPOINT_URL")

sqs = boto3.client("sqs", region_name=region, endpoint_url=endpoint)

def ensure_fifo(name: str):
    # FIFO 队列名必须以 .fifo 结尾
    attrs = {
        "FifoQueue": "true",
        "ContentBasedDeduplication": "true",  # 可用内容去重
        "ReceiveMessageWaitTimeSeconds": "0"  # 我们的动作是“非阻塞拉取”，保持 0
    }
    try:
        url = sqs.create_queue(QueueName=name, Attributes=attrs)["QueueUrl"]
        print("created:", name, url)
    except sqs.exceptions.QueueNameExists:
        url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
        print("exists:", name, url)
    return url

if __name__ == "__main__":
    ensure_fifo("device.demo.hp.fifo")
    ensure_fifo("device.demo.lp.fifo")
    # 按需：后续还会创建 llm.request.fifo / llm.complete.fifo 等
```

运行：

```
python scripts/bootstrap_sqs.py
```

---

## 3.4 SQS 适配器（替换 LocalBus）

> 语义对齐阶段 2：
>
> * `publish(topic, message)` ⇒ `SendMessage`（FIFO：需要 `MessageGroupId`；若不开内容去重则要 `MessageDeduplicationId`）
> * `consume(topic, timeout_ms)` ⇒ 非阻塞短轮询（`WaitTimeSeconds=0`），拿到就返回；拿不到返回 `None`（工作流下个 step 再试）
> * `qsize(topic)` ⇒ `GetQueueAttributes(ApproximateNumberOfMessages)`（可做本地缓存，避免过多 API 调用）

### `client/mq_sqs.py`

```python
import os, json, time, hashlib
import boto3
from botocore.config import Config

class SQSAdapter:
    def __init__(self, device_id: str, region: str | None = None, endpoint_url: str | None = None):
        region = region or os.getenv("AWS_REGION", "us-east-1")
        endpoint_url = endpoint_url or os.getenv("AWS_ENDPOINT_URL") or None
        self.client = boto3.client("sqs", region_name=region, endpoint_url=endpoint_url,
                                   config=Config(retries={"max_attempts": 3, "mode": "standard"}))
        self.device_id = device_id
        self.cache = {}  # queue_name -> url
        self._qsize_cache = {}  # queue_name -> (ts, value)

    def _queue_name(self, topic: str) -> str:
        # 约定：topic 直接就是队列名（含 .fifo）
        return topic

    def _url(self, queue_name: str) -> str:
        if queue_name in self.cache:
            return self.cache[queue_name]
        url = self.client.get_queue_url(QueueName=queue_name)["QueueUrl"]
        self.cache[queue_name] = url
        return url

    async def publish(self, topic: str, message: dict):
        qname = self._queue_name(topic)
        url = self._url(qname)
        body = json.dumps(message, ensure_ascii=False)
        # FIFO 需要 MessageGroupId；我们用 device_id 或 topic 自身
        group_id = self.device_id or topic
        # 开启 ContentBasedDeduplication 后可以不传 DeduplicationId；但带上更稳
        dedup = hashlib.md5(body.encode("utf-8")).hexdigest()
        self.client.send_message(
            QueueUrl=url,
            MessageBody=body,
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup
        )

    async def consume(self, topic: str, timeout_ms: int | None = None):
        qname = self._queue_name(topic)
        url = self._url(qname)
        # 非阻塞短轮询：WaitTimeSeconds=0；MaxNumberOfMessages=1
        resp = self.client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=0,
            VisibilityTimeout=20  # 20s 内未 ack 会再次投递
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            return None
        m = msgs[0]
        body = json.loads(m["Body"])
        # 把 receipt_handle 附在消息上，用于 ack / requeue
        body["_sqs_receipt"] = m["ReceiptHandle"]
        return body

    async def ack(self, topic: str, receipt: str):
        url = self._url(self._queue_name(topic))
        self.client.delete_message(QueueUrl=url, ReceiptHandle=receipt)

    async def requeue_now(self, topic: str, receipt: str):
        url = self._url(self._queue_name(topic))
        # 把可见性置 0，立刻重新可见
        self.client.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=0)

    def qsize(self, topic: str) -> int:
        # 近似值；简单做 200ms 缓存，避免过度调用
        qname = self._queue_name(topic)
        url = self._url(qname)
        now = time.time()
        ts_val = self._qsize_cache.get(qname)
        if ts_val and now - ts_val[0] < 0.2:
            return ts_val[1]
        attrs = self.client.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=["ApproximateNumberOfMessages"]
        )
        val = int(attrs["Attributes"].get("ApproximateNumberOfMessages", "0"))
        self._qsize_cache[qname] = (now, val)
        return val
```

---

## 3.5 把 SQS 接到 Services 里

### `client/services_sqs.py`

```python
import os
from core.context import Services
from .mq_sqs import SQSAdapter

def build_services_sqs(dom, osmod, vision, logger, device_id: str) -> Services:
    adapter = SQSAdapter(
        device_id=device_id,
        region=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None
    )
    # 给 actions 用的统一接口：同名方法
    class MQCompat:
        def __init__(self, sqs: SQSAdapter): self.sqs = sqs
        async def publish(self, topic: str, message): return await self.sqs.publish(topic, message)
        async def consume(self, topic: str, timeout_ms=None): return await self.sqs.consume(topic, timeout_ms)
        async def ack(self, topic: str, receipt: str): return await self.sqs.ack(topic, receipt)
        async def requeue_now(self, topic: str, receipt: str): return await self.sqs.requeue_now(topic, receipt)
        def qsize(self, topic: str) -> int: return self.sqs.qsize(topic)

    return Services(dom=dom, os=osmod, vision=vision, mq=MQCompat(adapter), logger=logger)
```

---

## 3.6 替换 MQ 动作（actions/mq.py）

> 维持阶段 2 的“非阻塞尝试”语义，新增 **ack**：

```python
import asyncio, json
from core.registry import register_action

@register_action("mq.publish")
def mq_publish(step, ctx, **_):
    topic = step["topic"]
    payload = step.get("payload", {})
    asyncio.get_event_loop().create_task(ctx.services.mq.publish(topic, payload))
    return {"ok": True, "topic": topic}

@register_action("mq.consume")
def mq_consume(step, ctx, **_):
    topic = step["topic"]
    save = step.get("save", "msg")
    # 如果队列近似长度为 0，直接返回 None（非阻塞）
    if ctx.services.mq.qsize(topic) == 0:
        return None
    async def _get():
        msg = await ctx.services.mq.consume(topic, timeout_ms=1)
        if msg is not None:
            ctx.vars[save] = msg
    asyncio.get_event_loop().create_task(_get())
    return "pending"

@register_action("mq.ack")
def mq_ack(step, ctx, **_):
    topic = step["topic"]
    receipt = step.get("receipt") or ctx.vars.get("_sqs_receipt") or \
              (ctx.vars.get(step.get("from_var","msg")) or {}).get("_sqs_receipt")
    if not receipt:
        return {"ok": False, "reason": "no receipt"}
    asyncio.get_event_loop().create_task(ctx.services.mq.ack(topic, receipt))
    return {"ok": True}
```

> 后续如果你更偏好**阻塞式长轮询**（`WaitTimeSeconds=20`），可以把 `mq.consume` 改成真正 await 的动作并把 Runner 的 `_run_action_async` 变成 `await fn(...)`，本阶段先维持“快步让出、频繁尝试”的方式，抢占会更灵敏。

---

## 3.7 示例工作流（SQS 版）

我们把阶段 2 的 demo 改为用 **SQS 队列名**（必须 `.fifo`）：

### `examples/stage3_lp_poller.json`

```json
{
  "name": "LP Poller (SQS)",
  "meta": { "priority": "LOW" },
  "start": "poll",
  "vars": { "tick": 0 },
  "states": {
    "poll": {
      "actions": [
        { "do": "demo.fake_red_dot", "save": "rd" },
        { "do": "branch", "if": "@rd['has_red'] == True", "then": "publish_hp", "else": "sleep" }
      ],
      "transitions": [
        { "if": "@rd['has_red'] == True", "go_to": "publish_hp" },
        { "go_to": "sleep" }
      ]
    },
    "sleep": {
      "actions": [ { "do": "set_variable", "name": "noop", "value": 0 } ],
      "transitions": [ { "go_to": "poll" } ]
    },
    "publish_hp": {
      "actions": [
        { "do": "mq.publish", "topic": "device.demo.hp.fifo", "payload": { "contact": "Alice", "text": "新消息..." } }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

### `examples/stage3_hp_responder.json`

```json
{
  "name": "HP Responder (SQS)",
  "meta": { "priority": "HIGH" },
  "start": "wait",
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "device.demo.hp.fifo", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None and @msg != 'pending'", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "set_variable", "name": "last_contact", "value": "@msg['contact']" },
        { "do": "set_variable", "name": "last_text", "value": "@msg['text']" },
        { "do": "mq.ack", "topic": "device.demo.hp.fifo", "from_var": "msg" }
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

> 注意：`mq.consume` 返回的 `msg` 我们直接把 `Body` 解析后的对象返回（里面含 `_sqs_receipt` 字段），因此 `send` 状态能抓到 `msg['contact']` 等，同时用 `mq.ack` 删除消息。

---

## 3.8 启动与联调

### 运行示例（给一个 `scripts/run_stage3_demo.py`）

```python
import asyncio, uuid, os, json, pathlib
from core.logging_setup import setup_logger
from core.context import Ctx
from core.runner import WorkflowRunner
from client.services_sqs import build_services_sqs

class DummyDOM: 
    def open(self, url): return {"ok": True}
    def exists(self, selector): return True
    def extract(self, query): return {"posts": []}
    def go_back(self): return {"ok": True}
class DummyOS:
    def move_to(self, x, y): pass
    def click(self): pass
    def scroll(self, px): pass
class DummyVision: pass

def load_spec(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

async def main():
    os.environ.setdefault("AWS_REGION", "us-east-1")
    os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")

    logger = setup_logger()
    services = build_services_sqs(DummyDOM(), DummyOS(), DummyVision(), logger, device_id="device.demo")

    lp_spec = load_spec("examples/stage3_lp_poller.json")
    lp_runner = WorkflowRunner(lp_spec, Ctx(services=services, run_id=str(uuid.uuid4())))

    hp_spec = load_spec("examples/stage3_hp_responder.json")
    hp_runner = WorkflowRunner(hp_spec, Ctx(services=services, run_id=str(uuid.uuid4())))

    # 复用阶段2的调度器
    from client.scheduler import Scheduler
    sched = Scheduler(hp_runner=hp_runner, lp_runners={"poller": lp_runner}, services=services)
    await sched.start()

if __name__ == "__main__":
    asyncio.run(main())
```

### 预期日志

```
.. | v=0.4.0 | INFO | action=demo.fake_red_dot ... priority=LOW
.. | v=0.4.0 | INFO | action=mq.publish ... priority=LOW       # 发布到 device.demo.hp.fifo
.. | v=0.4.0 | INFO | action=mq.consume ... priority=HIGH      # 立刻抢占，取到消息
.. | v=0.4.0 | INFO | action=set_variable ... priority=HIGH
.. | v=0.4.0 | INFO | action=mq.ack ... priority=HIGH
```

可以看到：一旦 LP 发布消息，**HP 立即抢占**并处理，再返回 LP。

---

## 3.9 成功标准

* 使用 **LocalStack** 的 **SQS FIFO** 队列，LP→HP 抢占流程运行稳定。
* 日志清晰显示 `mq.publish / mq.consume / mq.ack`；`ApproximateNumberOfMessages` 能驱动调度器判断是否抢占。
* 停掉 LocalStack 时，客户端报错清晰；重启后可恢复（重连逻辑由 boto3 负责，动作侧失败会抛异常并在日志中可见）。

---

## 3.10 迁移到真 AWS（生产）

* **去掉** `AWS_ENDPOINT_URL` 环境变量（或置空）；在部署环境通过角色或注入真实 AK/SK。
* 队列命名从 `device.demo.hp.fifo` → `device.<device_id>.hp.fifo`（或租户级）
* 按地域创建队列；在 **VPC 内网**（PrivateLink + Endpoint）访问可提升稳定性与安全。
* **成本/配额**：SQS API 有费用；`qsize` 查询频率不要过高（我们做了 200ms 缓存；线上建议 ≥ 500ms）。

---

## 3.11 注意事项与进阶

* **优先级**：SQS 无原生优先级；**用多队列**即可（我们已按 HP/LP 分队列）。
* **顺序与去重**：FIFO 通过 `MessageGroupId` 保序；`ContentBasedDeduplication` 可减少重复消息。
* **可见性超时**：HP 工作流若处理失败，未 `ack` 的消息将在 `VisibilityTimeout` 到期后重现；你可以在动作失败时调用 `mq.requeue_now` 立刻重试。
* **长轮询**：若将 `mq.consume` 改为真正 await 的动作，可把 `WaitTimeSeconds` 设为 10–20 秒，减少空转；当前为了“抢占灵敏”，保留非阻塞短轮询 + 调度器 `qsize()` 触发切换。
* **安全**：线上要基于 IAM 限定仅能访问本租户/本设备队列前缀（`device/<tenant>/<device_id>/*`）。

---

这一步落地完，你就完成了从 **内存队列 → SQS（LocalStack）** 的平滑迁移，并且**不改工作流与调度器写法**。
阶段4:
进入**阶段 4｜LLM 提交改为异步（云端回环）**。这一步把阶段 2 的“本地抢占”与阶段 3 的 “SQS 队列”串起来：**客户端只做 `llm.submit` → SQS（`llm.request.fifo`）→ 云端 Worker 拿到请求 →（可选真实 LLM/或先用 Mock）→ 校验/修复为结构化 JSON → 回投到设备 HP 队列 `device.<id>.hp.fifo` → 客户端 HP 工作流消费并执行**。做完后，你能看到：即使不用真实 LLM，也能端到端跑通“发→回”的闭环；换上真实 LLM（比如 OpenAI/DeepSeek）只需改环境变量。

---

# 4.1 目标

* 新增 `actions/llm.submit`：把 LLM 任务丢到 **SQS: `llm.request.fifo`**，包含 `job_id / job / device_target / prompt_pack / schema / inputs / provider_hint / idempotency_key` 等。
* 云端新增 **LLM Worker**（Node/JS）：消费 `llm.request.fifo`，路由（Mock/真实 LLM）、**JSON Schema 校验与自愈**，然后把结果投递到 **`device.<id>.hp.fifo`**。
* 客户端 **HP 工作流** 改成消费 device HP 队列并执行（阶段 3 的 responder 很接近，稍作调整）。
* 继续使用 **LocalStack** 本地联调；线上切换真 AWS 时无需改代码。

---

# 4.2 基础设施与队列

继续使用阶段 3 的 LocalStack。新增一个全局 FIFO 队列：

* `llm.request.fifo`（LLM 请求入口）

扩展你的启动脚本：

### `scripts/bootstrap_sqs.py`（在原有基础上添加）

```python
# ...（保留原有 import 与 ensure_fifo）
if __name__ == "__main__":
    ensure_fifo("device.demo.hp.fifo")
    ensure_fifo("device.demo.lp.fifo")
    ensure_fifo("llm.request.fifo")   # ★ 新增
```

运行：

```
python scripts/bootstrap_sqs.py
```

---

# 4.3 客户端改动：新增 llm.submit 动作 & 更新示例工作流

## 4.3.1 `actions/llm.py`

```python
import asyncio, uuid, time, hashlib
from core.registry import register_action
from core.expr import resolve

@register_action("llm.submit")
def llm_submit(step, ctx, **_):
    """
    step:
      job: "wechat_reply"
      prompt_pack: "wechat.sales.reply.v1"
      schema: "WeChatReplyV1"
      provider_hint: "openai" | "deepseek" | None
      inputs: <object or @var>
      device_target: <optional, default current device>  # 也可由云端决定
      idempotency_key: <optional>
    """
    device_target = step.get("device_target") or ctx.vars.get("device_id") or "device.demo"
    job = step["job"]
    job_id = str(uuid.uuid4())
    prompt_pack = step.get("prompt_pack")
    schema = step.get("schema")
    provider_hint = step.get("provider_hint")
    inputs = resolve(step.get("inputs", {}), ctx)

    idem = step.get("idempotency_key")
    if not idem:
        idem = f"{job}:{hashlib.md5(str(inputs).encode('utf-8')).hexdigest()}"

    payload = {
        "job": job,
        "job_id": job_id,
        "device_target": device_target,
        "prompt_pack": prompt_pack,
        "schema": schema,
        "provider_hint": provider_hint,
        "inputs": inputs,
        "idempotency_key": idem,
        "ts": int(time.time())
    }
    loop = asyncio.get_event_loop()
    loop.create_task(ctx.services.mq.publish("llm.request.fifo", payload))
    return {"ok": True, "enqueued": True, "job_id": job_id, "device_target": device_target}
```

> 说明：**客户端不直接调用 LLM**；统一走 `llm.request.fifo`。这保证了多模型路由、计量、Schema 校验都在云端集中处理。

## 4.3.2 LP 轮询工作流（把阶段 3 的发布改成 `llm.submit`）

### `examples/stage4_lp_poller.json`

```json
{
  "name": "LP Poller (SQS -> LLM)",
  "meta": { "priority": "LOW" },
  "start": "poll",
  "vars": { "tick": 0, "device_id": "device.demo" },
  "states": {
    "poll": {
      "actions": [
        { "do": "demo.fake_red_dot", "save": "rd" },
        { "do": "branch", "if": "@rd['has_red'] == True", "then": "submit_llm", "else": "sleep" }
      ],
      "transitions": [
        { "if": "@rd['has_red'] == True", "go_to": "submit_llm" },
        { "go_to": "sleep" }
      ]
    },
    "sleep": {
      "actions": [ { "do": "set_variable", "name": "noop", "value": 0 } ],
      "transitions": [ { "go_to": "poll" } ]
    },
    "submit_llm": {
      "actions": [
        {
          "do": "llm.submit",
          "job": "wechat_reply",
          "prompt_pack": "wechat.sales.reply.v1",
          "schema": "WeChatReplyV1",
          "provider_hint": "mock",                 // 先走 Mock，方便本地演示；换 openai/deepseek 即可
          "inputs": { "new_messages": [ { "contact": "Alice", "text": "在吗？" } ], "history": [] }
        }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

## 4.3.3 HP 响应工作流（消费 device HP 队列）

### `examples/stage4_hp_responder.json`

```json
{
  "name": "HP Responder (SQS <- LLM)",
  "meta": { "priority": "HIGH" },
  "start": "wait",
  "vars": { "device_id": "device.demo" },
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "device.demo.hp.fifo", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None && @msg != 'pending'", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "set_variable", "name": "last_contact", "value": "@msg['contact_name']" },
        { "do": "set_variable", "name": "last_reply", "value": "@msg['reply_text']" },
        { "do": "mq.ack", "topic": "device.demo.hp.fifo", "from_var": "msg" }
        // 阶段5会把这里换成 ext.focus_contact_by_anchor_name + os.type_and_send
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

---

# 4.4 云端 LLM Worker（Node/JS，兼容 LocalStack）

> 职责：**消费** `llm.request.fifo` → 路由（mock/真实）→ **Schema 校验** → **发布** 到 `device.<id>.hp.fifo`。
> 本地跑通用 **Mock**；接真实 LLM 时，填好 API Key 即可。

## 4.4.1 依赖

```
npm init -y
npm i @aws-sdk/client-sqs ajv ajv-formats openai
```

> `openai` 可换成你要的提供商 SDK（DeepSeek/Anthropic…）；若暂时无 Key，走 `MOCK_LLM=1`。

## 4.4.2 目录结构（server/）

```
server/
├─ worker.js
├─ router.js
├─ schema/
│  └─ WeChatReplyV1.json
└─ prompts/
   └─ wechat.sales.reply.v1.txt
```

### `server/schema/WeChatReplyV1.json`（最小版）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "WeChatReplyV1",
  "type": "object",
  "required": ["contact_name", "reply_text"],
  "properties": {
    "contact_name": { "type": "string" },
    "reply_text": { "type": "string" },
    "audit_rows": {
      "type": "array",
      "items": { "type": "object" }
    }
  },
  "additionalProperties": true
}
```

### `server/prompts/wechat.sales.reply.v1.txt`（简化）

```
你是销售助手。根据客户的最新消息生成一条简洁、礼貌、专业的中文回复。
输出严格为 JSON，符合 schema: { "contact_name": string, "reply_text": string }。
不要输出任何额外文本或注释。
客户信息:
{{inputs_json}}
```

### `server/router.js`

```js
const Ajv = require("ajv");
const addFormats = require("ajv-formats");
const fs = require("fs");
const path = require("path");
const { OpenAI } = require("openai");

function loadSchema(name) {
  const p = path.join(__dirname, "schema", name + ".json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}
function loadPrompt(name) {
  const p = path.join(__dirname, "prompts", name + ".txt");
  return fs.readFileSync(p, "utf-8");
}

function mustJSON(s) {
  // 粗暴提取第一段 JSON
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start >= 0 && end > start) {
    const sub = s.slice(start, end + 1);
    try { return JSON.parse(sub); } catch(e) {}
  }
  // 退化：返回一个最小对象
  return { reply_text: String(s).trim() };
}

async function callMock(job) {
  const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
  return { contact_name: nm, reply_text: `你好，${nm}，我在的哈～请问想了解哪款车？` };
}

async function callOpenAI(job, promptPack) {
  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const tpl = loadPrompt(promptPack);
  const inputs_json = JSON.stringify(job.inputs, null, 2);
  const content = tpl.replace("{{inputs_json}}", inputs_json);

  const res = await client.chat.completions.create({
    model: process.env.OPENAI_MODEL || "gpt-4o-mini",
    messages: [
      { role: "system", content: "You output only JSON that matches the given schema." },
      { role: "user", content }
    ],
    temperature: 0.3
  });
  const text = res.choices?.[0]?.message?.content || "{}";
  return mustJSON(text);
}

function makeValidator(schemaName) {
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);
  const schema = loadSchema(schemaName);
  const validate = ajv.compile(schema);
  return { validate, schema };
}

async function routeAndValidate(job) {
  const { schema: schemaName, prompt_pack: promptPack, provider_hint } = job;
  const { validate } = makeValidator(schemaName);
  let out;

  if (process.env.MOCK_LLM === "1" || provider_hint === "mock") {
    out = await callMock(job);
  } else if ((provider_hint || "").toLowerCase() === "openai") {
    out = await callOpenAI(job, promptPack);
  } else {
    // 你可以在这里接入 deepseek/anthropic，暂时 fallback 到 mock
    out = await callMock(job);
  }

  // 一轮修复与重试
  if (!validate(out)) {
    // 简单自愈：如果只有 reply_text，补齐 contact_name
    if (out.reply_text && !out.contact_name) {
      const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
      out.contact_name = nm;
    }
  }
  if (!validate(out)) {
    // 最终兜底
    const nm = job.inputs?.new_messages?.[0]?.contact || "客户";
    out = { contact_name: nm, reply_text: "好的，我已收到您的消息，稍后详细回复您～" };
  }
  return out;
}

module.exports = { routeAndValidate };
```

### `server/worker.js`

```js
const { SQSClient, ReceiveMessageCommand, DeleteMessageCommand, SendMessageCommand, GetQueueUrlCommand } = require("@aws-sdk/client-sqs");
const { routeAndValidate } = require("./router");

const region = process.env.AWS_REGION || "us-east-1";
const endpoint = process.env.AWS_ENDPOINT_URL || undefined; // LocalStack 用 http://localhost:4566
const sqs = new SQSClient({ region, endpoint });

async function getUrl(name) {
  const r = await sqs.send(new GetQueueUrlCommand({ QueueName: name }));
  return r.QueueUrl;
}

async function sendToDeviceHP(deviceId, body) {
  const qname = `${deviceId}.hp.fifo`.startsWith("device.") ? `${deviceId}.hp.fifo` : `device.${deviceId}.hp.fifo`;
  const QueueUrl = await getUrl(qname);
  const payload = JSON.stringify(body);
  await sqs.send(new SendMessageCommand({
    QueueUrl,
    MessageBody: payload,
    MessageGroupId: deviceId,
    MessageDeduplicationId: Buffer.from(payload).toString("base64").slice(0, 128)
  }));
}

async function loop() {
  const reqUrl = await getUrl("llm.request.fifo");
  console.log("[worker] listening", reqUrl);
  while (true) {
    const resp = await sqs.send(new ReceiveMessageCommand({
      QueueUrl: reqUrl,
      MaxNumberOfMessages: 1,
      WaitTimeSeconds: 3,     // 轻度长轮询
      VisibilityTimeout: 20
    }));
    const msgs = resp.Messages || [];
    if (msgs.length === 0) continue;

    for (const m of msgs) {
      const body = JSON.parse(m.Body);
      try {
        const out = await routeAndValidate(body);
        // 统一返回体：contact_name / reply_text / 透传 job_id & job
        const device = body.device_target || "device.demo";
        const result = {
          type: "llm.complete",
          job: body.job,
          job_id: body.job_id,
          contact_name: out.contact_name,
          reply_text: out.reply_text,
          audit_rows: out.audit_rows || []
        };
        await sendToDeviceHP(device, result);
        // ack request
        await sqs.send(new DeleteMessageCommand({ QueueUrl: reqUrl, ReceiptHandle: m.ReceiptHandle }));
        console.log("[worker] done job", body.job_id, "-> device", device);
      } catch (e) {
        console.error("[worker] error", e);
        // 不删除消息，让它超时重试（也可调 ChangeMessageVisibility 立刻重试）
      }
    }
  }
}

loop().catch(e => {
  console.error("[worker] fatal", e);
  process.exit(1);
});
```

> **要点**
>
> * Worker 支持 `MOCK_LLM=1` 本地无 Key 即可跑通。
> * 若你设置 `OPENAI_API_KEY` 且 `provider_hint=openai`，就会走真实调用。
> * 结果丢到 `device.<id>.hp.fifo`，客户端 HP 工作流立刻抢占。
> * 失败未 `DeleteMessage` 会在 `VisibilityTimeout` 后重现，便于容错。

---

# 4.5 启动与联调步骤

1. **启动 LocalStack（SQS）**

```
docker compose -f docker-compose.sqs.yml up -d
```

2. **创建队列**

```
python scripts/bootstrap_sqs.py
```

3. **启动云端 Worker（Mock 模式）**

```
cd server
export AWS_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566
export MOCK_LLM=1
node worker.js
```

> 想测真实 LLM：
>
> ```
> export MOCK_LLM=0
> export OPENAI_API_KEY=sk-xxx
> export OPENAI_MODEL=gpt-4o-mini
> node worker.js
> ```

4. **启动客户端（沿用阶段 3 的 demo main）**
   把 `examples/stage3_*` 替换为 **`stage4_lp_poller.json`** 与 **`stage4_hp_responder.json`**：

```
python scripts/run_stage3_demo.py
```

（或复制一个 `run_stage4_demo.py`，只改加载的两个 JSON 路径）

**预期日志（客户端）**：

```
.. | v=0.4.0 | INFO | action=demo.fake_red_dot ... priority=LOW
.. | v=0.4.0 | INFO | action=llm.submit ... priority=LOW   # → llm.request.fifo
.. | v=0.4.0 | INFO | action=mq.consume ... priority=HIGH  # ← device.demo.hp.fifo
.. | v=0.4.0 | INFO | action=set_variable ... priority=HIGH (last_contact=Alice)
.. | v=0.4.0 | INFO | action=mq.ack ... priority=HIGH
```

**预期日志（worker）**：

```
[worker] listening http://localhost:4566/000000000000/llm.request.fifo
[worker] done job <job_id> -> device device.demo
```

---

# 4.6 成功标准

* LP 每隔两步触发一次 `llm.submit`；云端 Worker 收到请求后，把结构化结果回投到设备 HP 队列；客户端 HP **立即抢占**并“发送”（此处用 set\_variable 模拟，阶段 5 会连真实 UI）。
* 断开 Worker 再重连：未消费的请求会保留并在 Worker 恢复后继续处理。
* 切换 `provider_hint=openai` 且填 `OPENAI_API_KEY`，即可走真实模型，输出仍然通过 **Schema 校验** 后返回。

---

# 4.7 风险与兜底

* **JSON 不合规**：Router 做了两次修复（轻度补齐 + 兜底生成）；仍失败则返回最小可用结构，避免阻塞 HP。
* **SQS 费用/频次**：本地无压力；线上请把 worker 的 `WaitTimeSeconds` 设为 10–20 秒减少空轮询。
* **幂等 & 去重**：已用 `ContentBasedDeduplication` 和 `idempotency_key`；若担心重复发送，可在云端再做一次（`llm_jobs` 表）去重（阶段 8 会加入数据库与计量）。
* **权限边界**：线上应使用 IAM 限制仅能访问本租户前缀；LocalStack 开发环境可共享默认密钥。

---

# 4.8 与后续阶段衔接

* **阶段 5**：把 HP 的 “send” 状态替换为真实 WeChat UI 操作（`ext.focus_contact_by_anchor_name` + `os.type_and_send`），并加入 `resource_lock=WECHAT_UI`。
* **阶段 6**：引入 **checkpoint（暂停/恢复/停止）**；在 LLM 提交前/后各打一个快照点。
* **阶段 8**：接入 **Postgres** 做 `prompt_packs / llm_schemas / llm_jobs / llm_usage`，LLM Router 真正上生产，支持“用户自带 API Key”。

---

到这里，**阶段 4** 已经把“客户端提交 LLM → 云端路由校验 → 设备 HP 抢占执行”的闭环打通了。

阶段5:
我们把**阶段 5** 重新设计成“**多桌面聊天工具通用方案**”，并落实三件事：

1. 设计一套**跨应用的 ChatApp 适配层**（WeChat/Slack/Telegram/WhatsApp Desktop/企业微信/钉钉等都能接）。
2. **OCR 必须本地离线**（客户端内置 OCR 引擎，无需云端算力/费用）。
3. 客户端**不得直连 Postgres**：所有数据写入一律通过云端 **API**（JWT 鉴权），支持离线重传。

下面是可直接落地的计划与代码骨架（延续你前面阶段 0–4 的项目结构），做完这一步，你不仅能跑通微信，还能很快扩到其它桌面聊天应用。

---

# 5.A 顶层改造概览

## 5.A.1 关键抽象

* **ChatAppAdapter**（每种聊天应用一个适配器）

  * `detect()`：是否已运行/找到窗口
  * `locate_window()`：返回窗口矩形与 DPI 缩放
  * `find_unread_badges()`：在“会话列表”区域找未读标记（红点/粗体/数字）
  * `open_conversation(target)`：打开指定会话（可用锚点图、快捷搜索、列表点击）
  * `capture_visible_messages()`：截取聊天区图像或从可访问性 API 直接取文本
  * `send_text(text)`：将文本发送到当前会话
  * `focus_contact_by_name(name)`：定位左侧联系人并聚焦（可选）
  * `get_rois()`：暴露各区域 ROI（left list/chat area/input box），可自动探测 + 静态回退

* **OCRService（本地）**

  * 封装 Tesseract（默认）与可选 PaddleOCR 插件；
  * 提供 `ocr_image(img, lang="chi_sim+eng", psm=6)`；
  * 轻量队列 + 节流，避免 OCR 占满 CPU；
  * 零网络依赖。

* **WindowManager**（跨平台）

  * Windows：pywinauto / win32gui / DPI aware
  * macOS：Quartz/CGWindowList + AX 可访问性（有权限更稳）
  * Linux：wmctrl / xdotool（可选）

* **资源锁**

  * 每种聊天应用一个锁：`CHAT_UI_<APP>`（例：`CHAT_UI_WECHAT`、`CHAT_UI_SLACK`）
  * 键鼠全局互斥锁（可选）：避免同时移动鼠标到不同应用

* **队列命名（SQS/FIFO）**

  * HP：`device.<id>.<app>.hp.fifo`
  * LP：`device.<id>.<app>.lp.fifo`
  * LLM 请求：`llm.request.fifo`（不变）

* **数据上报**

  * 只走 **API**：`/api/chats/upsert`、`/api/contacts/upsert`、`/api/events/ingest`
  * 客户端本地**离线队列**（WAL）断网缓存，恢复后批量提交
  * **禁止**客户端直连 Postgres

---

# 5.B 目录与文件新增

```
repo/
├─ client/
│  ├─ adapters/
│  │  ├─ base.py               # ChatAppAdapter 抽象
│  │  ├─ wechat.py             # 微信适配器
│  │  ├─ slack.py              # Slack 适配器（示例）
│  │  └─ registry.py           # 适配器注册与选择
│  ├─ ocr/
│  │  ├─ service.py            # 本地 OCR 封装（Tesseract / Paddle 插件）
│  │  └─ utils.py
│  ├─ api_client.py            # 统一 API 客户端（JWT、重试、离线队列）
│  ├─ services_sqs.py          # （已有）SQS 适配
│  ├─ scheduler.py             # （已有）增加 per-app HP 队列检查
│  └─ locks.py                 # （已有）
├─ actions/
│  ├─ chat_generic.py          # 通用聊天动作（调用 adapter）
│  ├─ api_actions.py           # 调用云端 API 上报/落库（代替直连 PG）
│  ├─ mq.py                    # （已有）
│  └─ llm.py                   # （已有）
├─ config/
│  ├─ apps.json                # 每个 app 的配置开关（是否启用、语言、阈值等）
│  ├─ profiles/
│  │  ├─ wechat.json           # 微信 ROI/锚点/行为偏好
│  │  └─ slack.json            # Slack ROI/锚点/行为偏好
│  └─ anchors/<app>/...        # 各应用锚点模板（红点、图标、联系人名）
└─ examples/
   ├─ stage5_lp_generic.json   # LP 通用工作流（按 app 参数工作）
   └─ stage5_hp_generic.json   # HP 通用工作流
```

---

# 5.C 核心代码骨架（可直接落地）

## 5.C.1 ChatAppAdapter 抽象

```python
# client/adapters/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

class ChatAppAdapter(ABC):
    name: str

    @abstractmethod
    def detect(self) -> bool: ...

    @abstractmethod
    def locate_window(self) -> Dict[str, int]:
        """返回 {"x":int,"y":int,"w":int,"h":int,"scale":float}"""

    @abstractmethod
    def get_rois(self) -> Dict[str, Dict[str,int]]:
        """返回 {"left_list": {...}, "chat_area": {...}, "input_box": {...}}"""

    @abstractmethod
    def find_unread_badges(self) -> List[Dict[str, Any]]:
        """返回未读标记列表：[{ "x":int,"y":int,"w":int,"h":int,"score":float }]"""

    @abstractmethod
    def open_conversation(self, target: Optional[str] = None) -> bool:
        """打开会话（未读最新或指定联系人）"""

    @abstractmethod
    def capture_visible_messages(self) -> Any:
        """返回截图图像（numpy array）或可访问性文本"""

    @abstractmethod
    def send_text(self, text: str) -> bool: ...

    def focus_contact_by_name(self, name: str) -> bool:
        """非必需；没有实现可直接返回 False"""
        return False
```

## 5.C.2 适配器注册与选择

```python
# client/adapters/registry.py
from typing import Dict, Optional
from .base import ChatAppAdapter
from .wechat import WeChatAdapter
from .slack import SlackAdapter

_REGISTRY: Dict[str, ChatAppAdapter] = {
    "wechat": WeChatAdapter(),
    "slack": SlackAdapter()
}

def get_adapter(app: str) -> Optional[ChatAppAdapter]:
    return _REGISTRY.get(app)
```

> 你可以逐步补充 `telegram`, `whatsapp`, `dingtalk`, `feishu` 等适配器。

## 5.C.3 微信适配器（MVP，截图+模板+键鼠；可后续升级 AX API）

```python
# client/adapters/wechat.py
import cv2, numpy as np, mss, pyautogui, json
from pathlib import Path
from .base import ChatAppAdapter

class WeChatAdapter(ChatAppAdapter):
    name = "wechat"
    def __init__(self):
        self.profile = json.loads(Path("config/profiles/wechat.json").read_text(encoding="utf-8"))

    def detect(self) -> bool:
        # MVP：通过窗口标题或进程名（后续可强化）
        return True

    def locate_window(self):
        # MVP：使用配置；后续可用 pygetwindow/Quartz 枚举真实窗口
        return self.profile["window"]

    def get_rois(self):
        return {
            "left_list": self.profile["left_list"],
            "chat_area": self.profile["chat_area"],
            "input_box": self.profile["input_box"]
        }

    def _grab(self, roi):
        with mss.mss() as sct:
            img = np.array(sct.grab({"top":roi["y"],"left":roi["x"],"width":roi["w"],"height":roi["h"]}))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def find_unread_badges(self):
        left = self.get_rois()["left_list"]
        img = self._grab(left)
        tpl = cv2.imread(self.profile["anchors"]["red_dot"])
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv >= self.profile["thresholds"]["red_dot"]:
            x = left["x"] + maxloc[0] + tpl.shape[1]//2
            y = left["y"] + maxloc[1] + tpl.shape[0]//2
            return [{"x":x,"y":y,"w":tpl.shape[1],"h":tpl.shape[0],"score":float(maxv)}]
        return []

    def open_conversation(self, target=None) -> bool:
        badges = self.find_unread_badges()
        if badges:
            b = badges[0]
            pyautogui.moveTo(b["x"]-30, b["y"], duration=0.12)
            pyautogui.doubleClick(); return True
        # 可选：target 名称定位（锚点文字/搜索框快捷键）
        return False

    def capture_visible_messages(self):
        chat = self.get_rois()["chat_area"]
        return self._grab(chat)

    def send_text(self, text: str) -> bool:
        ib = self.get_rois()["input_box"]
        pyautogui.click(ib["x"], ib["y"])
        pyautogui.typewrite(text, interval=0.03)
        pyautogui.press("enter")
        return True

    def focus_contact_by_name(self, name: str) -> bool:
        # MVP 可不实现，依赖 open_conversation 打开最新未读
        return False
```

> Slack/Telegram 等适配器实现方式相同；若能获取可访问性文本（如 Slack 可复制文本），就能**不依赖 OCR**，但 OCR 仍作为通用兜底。

## 5.C.4 本地 OCR Service

```python
# client/ocr/service.py
import pytesseract, numpy as np, cv2, threading, queue, time
from typing import Dict, Any

class OCRService:
    def __init__(self, lang="chi_sim+eng", psm=6):
        self.lang = lang; self.psm = psm
        self.q = queue.Queue(maxsize=8)
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.res = {}
        self.t.start()

    def _loop(self):
        while True:
            job_id, img = self.q.get()
            try:
                g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
                cfg = f"--psm {self.psm}"
                txt = pytesseract.image_to_string(b, lang=self.lang, config=cfg)
                self.res[job_id] = txt
            except Exception as e:
                self.res[job_id] = ""
            time.sleep(0.005)

    def submit(self, img: np.ndarray) -> str:
        jid = f"ocr-{time.time_ns()}"
        self.q.put((jid, img))
        return jid

    def fetch(self, job_id: str) -> str | None:
        return self.res.pop(job_id, None)
```

> 安装说明：
>
> * Windows：安装 Tesseract（含中文包 chi\_sim），将 `tesseract.exe` 路径加到 `PATH`；
> * macOS：`brew install tesseract tesseract-lang`.

## 5.C.5 通用聊天动作

```python
# actions/chat_generic.py
from core.registry import register_action
from client.adapters.registry import get_adapter
from client.ocr.service import OCRService
import numpy as np

_OCR = None

def _ocr():
    global _OCR
    if _OCR is None:
        _OCR = OCRService()
    return _OCR

@register_action("chat.find_unread")
def chat_find_unread(step, ctx, **_):
    app = step.get("app") or ctx.vars.get("app","wechat")
    ad = get_adapter(app)
    if not ad or not ad.detect():
        return {"has_unread": False}
    items = ad.find_unread_badges()
    return {"has_unread": len(items)>0, "items": items}

@register_action("chat.open_latest_unread")
def chat_open_latest_unread(step, ctx, **_):
    app = step.get("app") or ctx.vars.get("app","wechat")
    ad = get_adapter(app)
    ok = ad.open_conversation()
    return {"ok": ok}

@register_action("chat.capture_visible")
def chat_capture_visible(step, ctx, **_):
    app = step.get("app") or ctx.vars.get("app","wechat")
    ad = get_adapter(app)
    img = ad.capture_visible_messages()
    jid = _ocr().submit(img)
    return {"ocr_job": jid}

@register_action("chat.ocr_fetch")
def chat_ocr_fetch(step, ctx, **_):
    jid = step.get("job") or ctx.vars.get("ocr_job")
    txt = _ocr().fetch(jid)
    return {"done": txt is not None, "text": txt}

@register_action("chat.send_text")
def chat_send_text(step, ctx, **_):
    app = step.get("app") or ctx.vars.get("app","wechat")
    text = step["text"]
    ad = get_adapter(app)
    ok = ad.send_text(text)
    return {"ok": ok}

@register_action("chat.focus_contact")
def chat_focus_contact(step, ctx, **_):
    app = step.get("app") or ctx.vars.get("app","wechat")
    name = step["name"]
    ad = get_adapter(app)
    ok = ad.focus_contact_by_name(name)
    return {"ok": ok}
```

## 5.C.6 API 动作（代替直接写 PG）

```python
# client/api_client.py
import time, json, queue, threading, requests

class APIClient:
    def __init__(self, base, token):
        self.base = base; self.token = token
        self.q = queue.Queue(maxsize=1024)
        self.t = threading.Thread(target=self._loop, daemon=True); self.t.start()

    def _headers(self): return {"Authorization": f"Bearer {self.token}", "Content-Type":"application/json"}

    def _loop(self):
        while True:
            path, payload = self.q.get()
            try:
                requests.post(self.base+path, headers=self._headers(), data=json.dumps(payload), timeout=5)
            except Exception:
                # 简单重试/落地磁盘（略）
                time.sleep(1)

    def post_async(self, path, payload): self.q.put((path, payload))
```

```python
# actions/api_actions.py
from core.registry import register_action

@register_action("api.upsert_chats")
def api_upsert_chats(step, ctx, **_):
    rows = step["rows"]
    ctx.services.api.post_async("/api/chats/upsert", {"rows": rows})
    return {"ok": True, "n": len(rows)}

@register_action("api.ingest_event")
def api_ingest_event(step, ctx, **_):
    evt = step["event"]; payload = step.get("payload",{})
    ctx.services.api.post_async("/api/events/ingest", {"event":evt, "payload":payload})
    return {"ok": True}
```

> `Services` 里加 `api`：你已有 `build_services_sqs`，现在补一个 `api_client` 挂进去（JWT 登录后初始化）。云端 API 收到数据再写入 Postgres；客户端永不直连 DB。

---

# 5.D 通用 LP/HP 工作流（任意聊天 APP 通用）

## 5.D.1 LP（轮询→OCR→去重→提交 LLM）

```json
// examples/stage5_lp_generic.json
{
  "name": "Chat Poller (LP)",
  "meta": { "priority": "LOW", "resource_lock": "CHAT_UI_${app}" },
  "start": "poll",
  "vars": { "app": "wechat", "device_id": "device.demo" },
  "states": {
    "poll": {
      "actions": [
        { "do": "chat.find_unread", "save": "ur" },
        { "do": "branch", "if": "@ur['has_unread'] == True", "then": "open", "else": "sleep" }
      ],
      "transitions": [
        { "if": "@ur['has_unread'] == True", "go_to": "open" },
        { "go_to": "sleep" }
      ]
    },
    "sleep": { "actions": [ { "do": "wait_ms", "value": 1500 } ], "transitions": [ { "go_to": "poll" } ] },
    "open": {
      "actions": [
        { "do": "chat.open_latest_unread" },
        { "do": "wait_ms", "value": 300 },
        { "do": "chat.capture_visible", "save": "cap" }
      ],
      "transitions": [ { "go_to": "ocr_loop" } ]
    },
    "ocr_loop": {
      "actions": [
        { "do": "chat.ocr_fetch", "job": "@cap['ocr_job']", "save": "ocr" }
      ],
      "transitions": [
        { "if": "@ocr['done'] == True", "go_to": "post_ocr" },
        { "go_to": "ocr_loop" }
      ]
    },
    "post_ocr": {
      "actions": [
        { "do": "api.ingest_event", "event": "chat_visible_ocr", "payload": "@ocr" },
        { "do": "llm.submit",
          "job": "chat_reply",
          "prompt_pack": "wechat.sales.reply.v1",
          "schema": "WeChatReplyV1",
          "provider_hint": "mock",
          "inputs": { "new_messages_text": "@ocr['text']" }
        }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

> 注意：这里把 OCR 文本整体发给 LLM（MVP），后续你可以做更细的“新消息去重”逻辑（在云端 API 或客户端本地实现都行，但最终**写库走 API**）。

## 5.D.2 HP（消费 LLM 完成→定位联系人→发送）

```json
// examples/stage5_hp_generic.json
{
  "name": "Chat Responder (HP)",
  "meta": { "priority": "HIGH", "resource_lock": "CHAT_UI_${app}" },
  "start": "wait",
  "vars": { "app": "wechat", "device_id": "device.demo" },
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "device.demo.wechat.hp.fifo", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None && @msg != 'pending'", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "chat.focus_contact", "name": "@msg['contact_name']" },
        { "do": "wait_ms", "value": 200 },
        { "do": "chat.send_text", "text": "@msg['reply_text']" },
        { "do": "mq.ack", "topic": "device.demo.wechat.hp.fifo", "from_var": "msg" },
        { "do": "api.upsert_chats", "rows": [ { "contact": "@msg['contact_name']", "direction":"OUT", "text":"@msg['reply_text']" } ] }
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

> 对其它应用（如 Slack）：只要把 `vars.app` 改成 `slack`，HP 队列名改成 `device.demo.slack.hp.fifo`，就能用**同一套工作流**跑起来（适配器内部实现不同而已）。

---

# 5.E 兼容性与鲁棒性要点

* **检测优先级**：若适配器能通过可访问性 API 获取消息文本，优先走无 OCR 路径；OCR 作为兜底。
* **窗口定位**：先尝试自动定位（枚举窗口、匹配标题），失败再用静态 ROI；DPI 变化时按 `scale` 统一换算。
* **防封控**：键鼠操作加随机抖动/间隔；避免连续高频切换会话；提供“夜间限速”配置。
* **多 App 并行**：每个 App 一个资源锁；Scheduler 的 HP 检查改为**多队列**：

  * `device.<id>.wechat.hp.fifo`、`device.<id>.slack.hp.fifo` … 取任一有消息即抢占；
  * 抢占策略：**最近最早达的 HP 先执行**，或按固定优先顺序（可配）。
* **离线可用**：无网时 OCR 与自动化照常，所有 API 上报缓存至本地 WAL，恢复时批量提交。

---

# 5.F 落地步骤与验收

1. **接入适配器框架**：先完成 `wechat.py`（你已有视觉与键鼠基础，很快），复制一份做 `slack.py`（用 OCR 跑 MVP 即可）。
2. **本地 OCR**：引入 `client/ocr/service.py`，安装 Tesseract（含中文包），跑一个小脚本验证延迟与准确率。
3. **API 客户端**：填 `API_BASE` 与 `JWT`；把阶段 4/5 需要入库的内容改为 `api_actions.py` 动作上报。
4. **改造调度器 HP 检查**：从固定 `device.demo.hp.fifo` 改为**多 app 队列**的检查（取“任一非空”）。
5. **跑通通用工作流**：

   * LP：`stage5_lp_generic.json`（`vars.app=wechat`）
   * HP：`stage5_hp_generic.json`（HP 队列名含 `.wechat.`）
   * Worker 仍用阶段 4（Mock LLM 也可以），肉眼看到自动发送。
6. **复用到 Slack**：仅改 `vars.app=slack` 与 HP 队列名，验证**同一工作流**可用在第二款聊天工具。

**验收标准**

* 微信与 Slack 至少一个跑通（Slack 即使用 OCR 粗解析，也要能发送）。
* OCR 全在本地执行，抓包无外呼（除 API 上报/LLM）。
* 客户端进程内没有数据库驱动；Postgres 只在云端。
* HP 抢占在多 App 队列下仍然稳定（发送总是优先于继续轮询）。

---

# 5.G 接口与配置样例

**config/apps.json**

```json
{
  "wechat": { "enabled": true, "lang": "chi_sim+eng" },
  "slack": { "enabled": true, "lang": "eng" }
}
```

**config/profiles/wechat.json（示例）**

```json
{
  "window": {"x":0,"y":0,"w":1200,"h":800,"scale":1.0},
  "left_list": {"x":60,"y":100,"w":300,"h":650},
  "chat_area": {"x":380,"y":90,"w":800,"h":620},
  "input_box": {"x":400,"y":740},
  "anchors": { "red_dot": "config/anchors/wechat/red_dot.png" },
  "thresholds": { "red_dot": 0.85 }
}
```

**服务器 API（示意）**

* `POST /api/chats/upsert` `{ rows: [{contact, direction, text, ts?}] }`
* `POST /api/contacts/upsert` `{ contacts: [{name, source_app, anchor_hash?}] }`
* `POST /api/events/ingest` `{ event, payload }`

> 权限：JWT；入库：服务器把这些写入 Postgres。

阶段6:
进入**阶段 6｜Checkpoint：暂停 / 继续 / 停止（可恢复快照）**。这一阶段把你前面跑起来的 LP/HP 多工作流，加上**可中断、可恢复**能力，并做到：

* 任何时刻从云端发指令（或本地 CLI）→ 客户端在**安全点**落盘快照 → 释放 UI 锁 → 状态“PAUSED”。
* 继续时从快照恢复上下文（state、vars、未处理消息等），**不丢进度**。
* 停止时优雅清理：必要时把 SQS 消息**立即再可见**（requeue），并写入最终快照。
* 客户端**仍然只走 API** 上报快照和运行状态（不直连 Postgres）。
* 断网也能暂停/恢复：本地 WAL 缓存，网络恢复后自动补交。

下面给出**可直接落地**的改动清单、代码骨架、控制面协议、示例工作流与“怎么跑”的步骤。

---

# 6.A 设计要点

## 6.A.1 安全点（Safepoint）

* **动作级**：**不在动作中断**；只在**动作完成后**或**状态结束后**响应暂停/停止（避免半截点击/半截输入）。
* **资源锁**：到达安全点后**释放锁**（如 `CHAT_UI_WECHAT`），防止 UI 死锁。
* **消息一致性**：

  * 若正在处理 SQS 消息且未完成 → 使用 `mq.requeue_now`（VisibilityTimeout=0）让消息**立刻可见**，或记录 `receipt_handle` 到快照供恢复时继续 `ack/处理`。
  * LP 正在“提交 LLM”阶段不需要特别处理（`llm.request.fifo` 是持久的）。

## 6.A.2 快照内容（Snapshot）

```json
{
  "run_id": "...",
  "workflow_name": "...",
  "engine_version": "0.4.0",
  "state": "open_chat",
  "vars": { "...": "..." },             // 执行上下文（剔除不可序列化对象）
  "step_idx": 42,
  "resource_locks": ["CHAT_UI_WECHAT"],
  "inflight": {
    "sqs": { "topic": "device.demo.wechat.hp.fifo", "receipt": "..." },  // 可为空
    "ocr_job": "ocr-123...",                                             // 可为空
    "timers": []
  },
  "ts": 1737021234
}
```

> 注意：**不要**把大图像/模板丢进快照；留在 artifacts 目录即可。

## 6.A.3 控制面

* 新增**控制队列**：`device.<id>.control.fifo`（SQS）。云端/运维/管理台发指令（`PAUSE/RESUME/STOP`）。
* 客户端 Scheduler 抢占优先级：**CONTROL > HP > LP**。
* 同时保留 REST API：云端可触发 `/runs/:id/pause|resume|stop`，Server 再投送到 SQS 控制队列。
* 客户端收到 `RESUME`：拉取**云端最新快照**（REST），若离线则用**本地快照**。

---

# 6.B 目录与文件

```
repo/
├─ client/
│  ├─ checkpoint.py           # 快照序列化/反序列化 + 本地 WAL
│  ├─ run_manager.py          # 管理 run 生命周期与控制命令
│  ├─ scheduler.py            # （修改）支持 CONTROL 抢占
│  ├─ services_sqs.py         # （已有）
│  ├─ api_client.py           # （已有）补 /runs 与 /checkpoints
├─ actions/
│  ├─ checkpoint_actions.py   # 可选：工作流内显式保存快照
│  ├─ mq.py                   # 已有：补 requeue_now
│  └─ ...
├─ server/                    # （参考）API 约定，仅声明
│  └─ api_contract.md
└─ scripts/
   ├─ send_control.py         # 向 control 队列发 PAUSE/RESUME/STOP
   └─ run_stage6_demo.py      # 演示入口（LP+HP+控制）
```

---

# 6.C 客户端实现

## 6.C.1 快照工具

```python
# client/checkpoint.py
import json, time
from pathlib import Path
from typing import Dict, Any

def _sanitize_vars(vars: Dict[str, Any]) -> Dict[str, Any]:
    def ok(v):
        return isinstance(v, (str,int,float,bool,list,dict,type(None)))
    out = {}
    for k,v in vars.items():
        if ok(v): out[k]=v
        else: out[k]=str(v)  # 不可序列化的转字符串（日志用途）
    return out

class Checkpointer:
    def __init__(self, artifacts_dir="artifacts", api=None, logger=None):
        self.artifacts_dir = Path(artifacts_dir)
        self.api = api  # APIClient
        self.logger = logger

    def save(self, run_id: str, workflow_name: str, engine_version: str, state: str,
             vars: Dict[str,Any], step_idx: int, resource_locks: list[str], inflight: Dict[str,Any]):
        snap = {
            "run_id": run_id, "workflow_name": workflow_name, "engine_version": engine_version,
            "state": state, "vars": _sanitize_vars(vars), "step_idx": step_idx,
            "resource_locks": resource_locks, "inflight": inflight, "ts": int(time.time())
        }
        # 本地
        d = self.artifacts_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "checkpoint.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        # 云端（异步）
        if self.api:
            self.api.post_async("/api/runs/checkpoint", snap)
        if self.logger:
            self.logger.info(f"checkpoint saved state={state} step={step_idx}")
        return snap

    def load_local(self, run_id: str) -> Dict[str,Any] | None:
        p = self.artifacts_dir / run_id / "checkpoint.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
```

## 6.C.2 RunManager（接控制命令并操作 Runner）

```python
# client/run_manager.py
import asyncio
from typing import Dict, Any
from core import ENGINE_VERSION
from client.checkpoint import Checkpointer

class RunManager:
    def __init__(self, scheduler, services, locks):
        self.scheduler = scheduler
        self.services = services
        self.locks = locks
        self.checkpointer = Checkpointer(api=services.api, logger=services.logger)
        self._runs: Dict[str, Any] = {}  # run_id -> runner

    def register(self, run_id: str, runner):
        self._runs[run_id] = runner

    async def pause(self, run_id: str):
        r = self._runs.get(run_id)
        if not r: return
        # 等待到当前动作完成：由 Scheduler 在一步结束后调用 safepoint 回调
        r._pause_requested = True

    async def stop(self, run_id: str):
        r = self._runs.get(run_id)
        if not r: return
        r._stop_requested = True

    async def resume(self, run_id: str, snapshot: Dict[str,Any] | None = None):
        r = self._runs.get(run_id)
        if not r: return
        if not snapshot:
            snapshot = self.checkpointer.load_local(run_id)  # 若云端不可达，用本地
        if not snapshot: return
        # 恢复上下文
        r.state = snapshot["state"]
        r.ctx.vars.update(snapshot["vars"])
        r.step_idx = snapshot["step_idx"]
        r._paused = False
        self.services.logger.info(f"resumed run={run_id} state={r.state}")

    async def at_safepoint(self, runner):
        """由 Scheduler/Runner 在每个动作后调用：检查是否需要暂停/停止；如需要则保存快照。"""
        if getattr(runner, "_stop_requested", False):
            await self._save_and_cleanup(runner, status="STOPPED")
            runner.state = None
            return True
        if getattr(runner, "_pause_requested", False):
            await self._save_and_cleanup(runner, status="PAUSED")
            runner._paused = True
            return True
        return False

    async def _save_and_cleanup(self, runner, status: str):
        inflight = {}
        # 如果当前有未 ack 的 SQS 消息且需要立即可见，调用 requeue_now
        receipt = runner.ctx.vars.get("_sqs_receipt")
        topic = runner.ctx.vars.get("_sqs_topic")
        if receipt and topic:
            await self.services.mq.requeue_now(topic, receipt)
            inflight["sqs"] = {"topic": topic, "receipt": receipt}
        inflight["ocr_job"] = runner.ctx.vars.get("ocr_job")
        # 释放锁由 Scheduler 确保在 step 出口执行
        self.checkpointer.save(
            run_id=runner.ctx.run_id, workflow_name=runner.spec.get("name"),
            engine_version=ENGINE_VERSION, state=runner.state, vars=runner.ctx.vars,
            step_idx=runner.step_idx, resource_locks=[runner.spec.get("meta",{}).get("resource_lock")],
            inflight=inflight
        )
        # 上报运行状态（API）
        self.services.api.post_async("/api/runs/status", {
            "run_id": runner.ctx.run_id, "status": status, "state": runner.state
        })
```

## 6.C.3 修改 Scheduler：增加 CONTROL 抢占 & Safepoint 钩子

```python
# client/scheduler.py（节选）
class Scheduler:
    def __init__(self, hp_runner, lp_runners, services, locks, run_manager):
        self.hp_runner = hp_runner
        self.lp_runners = lp_runners
        self.services = services
        self.locks = locks
        self.rm = run_manager

    def _control_pending(self) -> bool:
        # CONTROL 队列非空则最高优先级
        return self.services.mq.qsize("device.demo.control.fifo") > 0

    async def _run_step_with_lock(self, runner, should_preempt):
        lock_name = runner.spec.get("meta",{}).get("resource_lock")
        lock = self.locks.get(lock_name) if lock_name else None
        if lock: await lock.acquire()
        try:
            # 若该 runner 被标记为 paused，直接跳过
            if getattr(runner, "_paused", False):
                return
            await runner.step(lambda: self._control_pending() or await should_preempt())
            # 每个动作后，runner.step 会归来一次，这里调用 safepoint 检查
            if await self.rm.at_safepoint(runner):
                # paused/stopped：不再继续本 step
                return
        finally:
            if lock and lock.locked(): lock.release()

    async def _loop_control(self):
        # 监听 CONTROL 队列并对 run_manager 下压命令
        while True:
            msg = await self.services.mq.consume("device.demo.control.fifo", timeout_ms=500)
            if msg:
                cmd = (msg.get("cmd") or "").upper()
                run_id = msg.get("run_id")
                if cmd == "PAUSE": await self.rm.pause(run_id)
                elif cmd == "STOP": await self.rm.stop(run_id)
                elif cmd == "RESUME": await self.rm.resume(run_id, snapshot=None)  # 云端获取可在 API 动作里做
                await self.services.mq.ack("device.demo.control.fifo", msg["_sqs_receipt"])

    async def start(self):
        await asyncio.gather(self._loop_control(), self._loop_hp(), self._loop_lp())
```

> **要点**
>
> * `runner.step(should_preempt)` 每个动作后都会把控制权还给调度器；我们在 `_run_step_with_lock` 的“动作后”调用 `run_manager.at_safepoint()`，如果有暂停/停止请求，就保存快照并不再继续。
> * CONTROL 抢占通过 `_control_pending()` 直接让 `should_preempt()` 返回 True 实现。

## 6.C.4 Runner：标记字段

在你的 `core/runner.py`（阶段 2 的异步版）里给 `WorkflowRunner.__init__` 加：

```python
self._pause_requested = False
self._stop_requested = False
self._paused = False
```

其余逻辑无需改动。

## 6.C.5 动作：显式保存快照（可选）

```python
# actions/checkpoint_actions.py
from core.registry import register_action

@register_action("checkpoint.save")
def cp_save(step, ctx, **_):
    # 显式在工作流关键点保存（例如 LLM 提交前后）
    rm = ctx.services.run_manager
    rm.checkpointer.save(
        run_id=ctx.run_id,
        workflow_name=ctx.vars.get("_workflow_name",""),
        engine_version=ctx.vars.get("_engine_version","0.4.0"),
        state=ctx.vars.get("_state",""),
        vars=ctx.vars,
        step_idx=ctx.vars.get("_step_idx",0),
        resource_locks=[ctx.vars.get("_lock")],
        inflight={}
    )
    return {"ok": True}
```

> 日常不必须；你也可以在工作流重要 state（如 `submit_llm` 前）手工插入。

---

# 6.D 云端 API 合约（摘要）

> 服务器写入 Postgres；客户端只调 API，不直连 DB。

* `POST /api/runs/checkpoint`
  Body：见上文 `snapshot`；Server：`INSERT ... ON CONFLICT (run_id) DO UPDATE`
* `POST /api/runs/status`
  `{ run_id, status: "RUNNING|PAUSED|STOPPED|DONE|FAILED", state }`
* `POST /api/runs/:id/pause|resume|stop`
  Server 将命令投递到 `device.<id>.control.fifo`，并返回 202。
* `GET /api/runs/:id/checkpoint`
  返回**最新快照**；客户端 `resume` 时优先拉这个（若失败再读本地）。

> 认证：JWT；幂等：`run_id` 作为键；审计：写 `runs_status_history` 表。

---

# 6.E 示例：LP/HP 工作流小改（插入可恢复点）

> **LP（摘自阶段 5 通用 LP）**：在 `post_ocr` 前后各加一个显式 checkpoint（可选）。

```json
{
  "name": "Chat Poller (LP)",
  "meta": { "priority": "LOW", "resource_lock": "CHAT_UI_${app}" },
  "start": "poll",
  "vars": { "app": "wechat", "device_id": "device.demo" },
  "states": {
    "...": {},
    "post_ocr": {
      "actions": [
        { "do": "checkpoint.save" },
        { "do": "api.ingest_event", "event": "chat_visible_ocr", "payload": "@ocr" },
        { "do": "llm.submit", "...": "..." },
        { "do": "checkpoint.save" }
      ],
      "transitions": [ { "go_to": "poll" } ]
    }
  }
}
```

> **HP** 无需改；暂停时如果正处于 `send`，Safepoint 会 requeue 消息或在快照记录 `receipt`，下次恢复继续处理。

---

# 6.F 控制命令发送脚本（开发/演示）

```python
# scripts/send_control.py
import os, json, sys
import boto3
device = os.getenv("DEVICE_ID","device.demo")
cmd = sys.argv[1].upper()     # PAUSE | RESUME | STOP
run_id = sys.argv[2]
queue = f"{device}.control.fifo" if device.startswith("device.") else f"device.{device}.control.fifo"

sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION","us-east-1"),
                   endpoint_url=os.getenv("AWS_ENDPOINT_URL","http://localhost:4566"))
url = sqs.get_queue_url(QueueName=queue)["QueueUrl"]
body = json.dumps({"cmd": cmd, "run_id": run_id})
sqs.send_message(QueueUrl=url, MessageBody=body, MessageGroupId=device, MessageDeduplicationId=run_id+cmd)
print("ok")
```

---

# 6.G 运行步骤（本地 LocalStack）

1. **确保阶段 4/5 运行正常**（LocalStack、LLM Worker、客户端 LP/HP）。

2. **创建 control 队列**：更新 `scripts/bootstrap_sqs.py` 增加

   ```python
   ensure_fifo("device.demo.control.fifo")
   ```

   然后运行：

   ```
   python scripts/bootstrap_sqs.py
   ```

3. **启动客户端（带 RunManager）**：示例 `scripts/run_stage6_demo.py`

   ```python
   import asyncio, uuid, os, json, pathlib
   from core.logging_setup import setup_logger
   from core.context import Ctx
   from core.runner import WorkflowRunner
   from client.services_sqs import build_services_sqs
   from client.scheduler import Scheduler
   from client.locks import ResourceLocks
   from client.run_manager import RunManager

   def load(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

   async def main():
       logger = setup_logger()
       services = build_services_sqs(DummyDOM(), DummyOS(), DummyVision(), logger, device_id="device.demo")
       locks = ResourceLocks()
       # 挂 run_manager 到 services，供 actions/checkpoint 使用
       run_manager = RunManager(scheduler=None, services=services, locks=locks)
       services.run_manager = run_manager

       lp = WorkflowRunner(load("examples/stage5_lp_generic.json"), Ctx(services=services, run_id=str(uuid.uuid4())))
       hp = WorkflowRunner(load("examples/stage5_hp_generic.json"), Ctx(services=services, run_id=str(uuid.uuid4())))
       run_manager.register(lp.ctx.run_id, lp)
       run_manager.register(hp.ctx.run_id, hp)

       sched = Scheduler(hp_runner=hp, lp_runners={"poller": lp}, services=services, locks=locks, run_manager=run_manager)
       run_manager.scheduler = sched

       await sched.start()

   if __name__ == "__main__":
       asyncio.run(main())
   ```

   > `DummyDOM/DummyOS/DummyVision` 与阶段 5 相同或替换为真实适配器。

4. **发控制命令**：

   * 控制台打印 `lp.run_id`、`hp.run_id`（你可以在启动时 `logger.info` 打印）。
   * 暂停 LP：

     ```
     python scripts/send_control.py PAUSE <lp_run_id>
     ```

     期望：日志出现 `checkpoint saved state=...`，LP 不再继续；HP 仍可工作。
   * 继续 LP：

     ```
     python scripts/send_control.py RESUME <lp_run_id>
     ```

     期望：日志出现 `resumed run=<id> state=...`，LP 从原状态继续。
   * 停止 HP：

     ```
     python scripts/send_control.py STOP <hp_run_id>
     ```

---

# 6.H 验收标准

* **PAUSE**：在 1–2 个动作延迟内停下（Safepoint），写本地 `artifacts/<run_id>/checkpoint.json` 并通过 `/api/runs/checkpoint` 上报；UI 锁释放。
* **RESUME**：从快照恢复**同一 state** 与关键 `vars`，继续执行；HP/LP 互不影响。
* **STOP**：写终止快照；如有未 ack 的 SQS 消息则 `requeue_now` 或在快照记录 `receipt` 供未来处理。
* **离线**：断开网络后 `PAUSE` 仍能保存本地快照；网络恢复后 `/api/runs/checkpoint`、`/api/runs/status` 被补交。
* **不直连 DB**：抓包可见客户端仅访问 REST API 与 SQS；无直连 Postgres 的连接。

---

# 6.I 风险与兜底

* **动作耗时过长导致暂停不及时**：把长动作拆小（例如 OCR 拆成 capture 与 fetch 两步），或在长动作内部插入可中断点（后续阶段 11 优化）。
* **快照过大**：`_sanitize_vars` 仅保留可序列化基础类型；大对象转字符串/路径引用。
* **SQS 可见性窗口**：HP 处理中途暂停可能造成消息再次可见 → 允许；若必须“至少一次且不重复”，用 `idempotency_key` 在云端消费侧去重。
* **多 App 并行**：每 App 一个控制队列或在同队列里带 `app` 字段过滤；CONTROL 仍最高优先级。

---

到这里，**阶段 6** 的“可暂停/可恢复/可停止 + 云端控制 + API-only 落库”已经端到端落地。
*阶段 7｜登录 / 设备注册 / 机器识别码**。这一阶段做完后，你将：

* 在客户端看到**登录窗**（或 CLI 登录），首次登录会生成并绑定**机器识别码 machine\_code**；
* 设备在云端注册为 `device_id`，并把能力集（支持的 Chat App、OCR、本地 OS 等）上报；
* 基于**订阅计划**（device\_limit）在**服务端 API**层做准入校验（客户端**不直连 Postgres**）；
* SQS 队列统一使用 `device_id`（或 `device_id+app`）命名，彻底接入前面的 LP/HP 与控制通道。

下面是可**直接落地**的实现包：目录、DB 表、服务端 API、客户端改造、如何跑、验收与兜底。

---

# 7.A 目录与文件（新增/改动）

```
repo/
├─ server/                        # 新增：Auth & Devices API（Node/Express + Postgres）
│  ├─ package.json
│  ├─ .env.example
│  ├─ src/
│  │  ├─ index.js                 # Express 启动
│  │  ├─ db.js                    # pg 连接池
│  │  ├─ auth.js                  # /auth/* 路由
│  │  ├─ devices.js               # /devices/* 路由
│  │  ├─ middleware.js            # JWT 校验
│  │  └─ plans.js                 # 计划配置与校验
│  └─ sql/
│     └─ init.sql                 # 表结构与种子数据
├─ docker-compose.stage7.yml      # Postgres + server 一键起
├─ client/
│  ├─ login_ui.py                 # 客户端登录（Tkinter 简易版，或 CLI）
│  ├─ machine_code.py             # 机器码生成/持久化（UUIDv4）
│  ├─ api_client.py               # 扩充：登录/刷新令牌/设备注册/心跳
│  ├─ services_sqs.py             # 改：使用 device_id 组装队列名
│  ├─ services_build.py           # 新：统一构建 Services（含 api/mq 等）
│  └─ scheduler.py                # 改：HP 队列名来自 device_id + app
├─ examples/
│  ├─ stage7_lp_generic.json      # 把队列名占位改为 ${device_id}.${app}.hp.fifo
│  └─ stage7_hp_generic.json
└─ scripts/
   └─ run_stage7_demo.py          # 启动顺序：登录→设备注册→跑 LP/HP
```

---

# 7.B 服务端（Node/Express + Postgres）

## 7.B.1 docker-compose（本地起 Postgres 与 API）

```yaml
# docker-compose.stage7.yml
version: "3.9"
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: autoagent
    ports: ["5432:5432"]
    volumes: ["./server/sql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro"]

  api:
    image: node:20
    working_dir: /app
    command: bash -lc "npm i && node src/index.js"
    volumes:
      - ./server:/app
    environment:
      DATABASE_URL: postgres://app:app@db:5432/autoagent
      JWT_SECRET: dev_secret_change_me
    depends_on: [db]
    ports: ["8080:8080"]
```

## 7.B.2 初始化表结构（**只在服务端**连 Postgres）

```sql
-- server/sql/init.sql
create extension if not exists "uuid-ossp";

create table if not exists users(
  id uuid primary key default uuid_generate_v4(),
  email text unique not null,
  password_hash text not null,
  created_at timestamptz default now(),
  status int default 1
);

create table if not exists subscriptions(
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  plan text not null,            -- free/pro/team
  device_limit int not null,
  hp_concurrency int not null default 1,
  status text not null default 'active',
  started_at timestamptz default now(),
  ends_at timestamptz
);

create table if not exists devices(
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  machine_code text not null unique,
  name text,
  status int default 1,
  capabilities jsonb default '{}'::jsonb,
  last_seen timestamptz,
  created_at timestamptz default now()
);

-- 演示用：一条默认订阅（你也可通过 API 创建）
insert into users (email, password_hash)
  values ('demo@acme.com', '$2b$10$1b3vQv6Yq0m2wqvI2l9C9e7T4l0tYf4e4iQG3qzjH2lq4rYxQfQG6') 
  on conflict do nothing; -- 'demo123'（bcrypt 示例，实际请更换）

insert into subscriptions (user_id, plan, device_limit, hp_concurrency)
  select id, 'pro', 3, 2 from users where email='demo@acme.com'
  on conflict do nothing;
```

> 上面 `password_hash` 请自行用 bcrypt 生成；示例仅便于演示。

## 7.B.3 server/package.json

```json
{
  "name": "autoagent-api",
  "type": "module",
  "dependencies": {
    "bcryptjs": "^2.4.3",
    "cors": "^2.8.5",
    "express": "^4.19.2",
    "jsonwebtoken": "^9.0.2",
    "pg": "^8.11.5"
  }
}
```

## 7.B.4 src/db.js

```js
import pkg from "pg";
const { Pool } = pkg;
export const pool = new Pool({ connectionString: process.env.DATABASE_URL });
```

## 7.B.5 src/middleware.js（JWT 中间件）

```js
import jwt from "jsonwebtoken";

export function authRequired(req, res, next) {
  const h = req.headers.authorization || "";
  const token = h.startsWith("Bearer ") ? h.slice(7) : null;
  if (!token) return res.status(401).json({ error: "no token" });
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET || "dev");
    req.user = payload; // {user_id}
    next();
  } catch (e) {
    res.status(401).json({ error: "bad token" });
  }
}
```

## 7.B.6 src/plans.js（计划与设备数校验）

```js
import { pool } from "./db.js";

export async function ensureDeviceAllowance(user_id) {
  const { rows: subs } = await pool.query(
    "select device_limit from subscriptions where user_id=$1 and status='active' order by started_at desc limit 1",
    [user_id]
  );
  const limit = subs[0]?.device_limit ?? 1;
  const { rows: cnt } = await pool.query(
    "select count(*)::int as n from devices where user_id=$1 and status=1",
    [user_id]
  );
  if ((cnt[0]?.n ?? 0) >= limit) {
    const err = new Error("device limit reached");
    err.code = "DEVICE_LIMIT";
    throw err;
  }
}
```

## 7.B.7 src/auth.js（注册/登录/刷新）

```js
import express from "express";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { pool } from "./db.js";
export const auth = express.Router();

auth.post("/register", async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: "bad params" });
  const hash = await bcrypt.hash(password, 10);
  const { rows } = await pool.query(
    "insert into users(email,password_hash) values($1,$2) returning id,email",
    [email, hash]
  );
  return res.json({ user: rows[0] });
});

auth.post("/login", async (req, res) => {
  const { email, password } = req.body || {};
  const { rows } = await pool.query("select id,password_hash from users where email=$1", [email]);
  const u = rows[0];
  if (!u) return res.status(401).json({ error: "bad creds" });
  const ok = await bcrypt.compare(password, u.password_hash);
  if (!ok) return res.status(401).json({ error: "bad creds" });
  const token = jwt.sign({ user_id: u.id }, process.env.JWT_SECRET || "dev", { expiresIn: "8h" });
  return res.json({ access_token: token, user: { id: u.id, email } });
});
```

## 7.B.8 src/devices.js（设备注册/心跳/注销）

```js
import express from "express";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import { ensureDeviceAllowance } from "./plans.js";

export const devices = express.Router();

devices.post("/register", authRequired, async (req, res) => {
  const user_id = req.user.user_id;
  const { machine_code, name, capabilities } = req.body || {};
  if (!machine_code) return res.status(400).json({ error: "no machine_code" });

  // 已存在则重绑定到当前用户（或直接返回）
  const { rows: existing } = await pool.query("select * from devices where machine_code=$1", [machine_code]);
  if (existing.length) {
    // 若已属于其他用户，可以拒绝或转移；这里假设转移需要权限，先简单允许重绑给同一用户
    if (existing[0].user_id !== user_id) {
      // 也可以返回 409 让前端提示
    }
    const { rows } = await pool.query(
      "update devices set user_id=$1, name=$2, capabilities=$3, status=1, last_seen=now() where machine_code=$4 returning id",
      [user_id, name || existing[0].name, capabilities || existing[0].capabilities, machine_code]
    );
    return res.json({ device_id: rows[0].id, reused: true });
  }

  await ensureDeviceAllowance(user_id);
  const { rows } = await pool.query(
    "insert into devices(user_id,machine_code,name,capabilities,last_seen) values($1,$2,$3,$4,now()) returning id",
    [user_id, machine_code, name || null, capabilities || {}]
  );
  return res.json({ device_id: rows[0].id, reused: false });
});

devices.post("/heartbeat", authRequired, async (req, res) => {
  const user_id = req.user.user_id;
  const { device_id } = req.body || {};
  if (!device_id) return res.status(400).json({ error: "no device_id" });
  await pool.query("update devices set last_seen=now() where id=$1 and user_id=$2", [device_id, user_id]);
  return res.json({ ok: true });
});
```

## 7.B.9 src/index.js（启动）

```js
import express from "express";
import cors from "cors";
import { auth } from "./auth.js";
import { devices } from "./devices.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));
app.get("/healthz", (req, res) => res.json({ ok: true }));
app.use("/auth", auth);
app.use("/devices", devices);
const port = process.env.PORT || 8080;
app.listen(port, () => console.log("api listening on", port));
```

---

# 7.C 客户端改造

## 7.C.1 机器识别码（仅本地生成与持久化）

```python
# client/machine_code.py
import uuid, json
from pathlib import Path

def get_machine_code():
    p = Path.home()/".autoagent"/"device.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["machine_code"]
    mc = str(uuid.uuid4())
    p.write_text(json.dumps({"machine_code": mc}, ensure_ascii=False, indent=2), encoding="utf-8")
    return mc
```

## 7.C.2 登录窗（或 CLI 登录）

```python
# client/login_ui.py  （可替换为 CLI：input(email/password)）
import tkinter as tk
import requests, json
from pathlib import Path

def login_and_save(api_base):
    root = tk.Tk(); root.title("Login")
    tk.Label(root, text="Email").grid(row=0, column=0); e1 = tk.Entry(root); e1.grid(row=0, column=1)
    tk.Label(root, text="Password").grid(row=1, column=0); e2 = tk.Entry(root, show="*"); e2.grid(row=1, column=1)
    result = {}
    def do_login():
        try:
            r = requests.post(api_base+"/auth/login", json={"email": e1.get(), "password": e2.get()}, timeout=5)
            r.raise_for_status()
            data = r.json()
            Path.home().joinpath(".autoagent","auth.json").parent.mkdir(parents=True, exist_ok=True)
            Path.home().joinpath(".autoagent","auth.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            result["token"] = data["access_token"]; root.destroy()
        except Exception as e:
            tk.Label(root, text=f"Error: {e}").grid(row=3, column=0, columnspan=2)
    tk.Button(root, text="Login", command=do_login).grid(row=2, column=0, columnspan=2)
    root.mainloop()
    return result.get("token")
```

## 7.C.3 API 客户端扩展（登录/注册设备/心跳）

```python
# client/api_client.py （在原基础上补充）
import time, json, queue, threading, requests
from pathlib import Path

class APIClient:
    def __init__(self, base, token=None):
        self.base = base; self.token = token or self._load_token()
        self.q = queue.Queue(maxsize=1024)
        self.t = threading.Thread(target=self._loop, daemon=True); self.t.start()

    def _load_token(self):
        p = Path.home()/".autoagent"/"auth.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("access_token")
        return None

    def set_token(self, token): self.token = token

    def _headers(self): return {"Authorization": f"Bearer {self.token}", "Content-Type":"application/json"} if self.token else {"Content-Type":"application/json"}

    def post(self, path, payload):
        r = requests.post(self.base+path, headers=self._headers(), data=json.dumps(payload), timeout=8)
        r.raise_for_status()
        return r.json()

    # 异步上报（WAL）
    def _loop(self):
        while True:
            path, payload = self.q.get()
            try:
                self.post(path, payload)
            except Exception:
                time.sleep(1)

    def post_async(self, path, payload): self.q.put((path, payload))

    # === 新增：设备注册与心跳 ===
    def register_device(self, machine_code, name, capabilities):
        return self.post("/devices/register", {"machine_code": machine_code, "name": name, "capabilities": capabilities})

    def heartbeat(self, device_id):
        self.post_async("/devices/heartbeat", {"device_id": device_id})
```

## 7.C.4 统一构建 Services（含 API / SQS）

```python
# client/services_build.py
import os
from client.services_sqs import build_services_sqs
from client.api_client import APIClient
from client.machine_code import get_machine_code

def build_services(api_base, dom, osmod, vision, logger, device_name="My Device", apps=None):
    api = APIClient(api_base)
    token = api.token
    if not token:
        from client.login_ui import login_and_save
        token = login_and_save(api_base)
        api.set_token(token)

    mc = get_machine_code()
    capabilities = {
        "apps": apps or ["wechat"],
        "ocr": "tesseract",
        "os": os.name
    }
    reg = api.register_device(mc, device_name, capabilities)
    device_id = reg["device_id"]

    # SQS services 用 device_id
    services = build_services_sqs(dom, osmod, vision, logger, device_id=device_id)
    services.api = api
    services.device_id = device_id
    services.machine_code = mc
    # 心跳后台
    import threading, time
    def _hb():
        while True:
            try: api.heartbeat(device_id)
            except: pass
            time.sleep(30)
    threading.Thread(target=_hb, daemon=True).start()
    return services
```

## 7.C.5 队列命名改造（device\_id + app）

* HP 队列：`device.<device_id>.<app>.hp.fifo`
* LP 队列（如有）：`device.<device_id>.<app>.lp.fifo`
* CONTROL 队列：`device.<device_id>.control.fifo`（不分 app）

修改**Scheduler**里对 HP 队列的检查，按当前运行的 `app` 生成队列名。

```python
# scheduler 中的示例（节选）
def hp_topic_for(services, app):
    return f"device.{services.device_id}.{app}.hp.fifo"

# 检查是否有 HP 消息
return self.services.mq.qsize(hp_topic_for(self.services, runner.ctx.vars.get("app","wechat"))) > 0
```

## 7.C.6 示例工作流（把硬编码队列改为占位）

```json
// examples/stage7_hp_generic.json
{
  "name": "Chat Responder (HP)",
  "meta": { "priority": "HIGH", "resource_lock": "CHAT_UI_${app}" },
  "start": "wait",
  "vars": { "app": "wechat" },
  "states": {
    "wait": {
      "actions": [
        { "do": "mq.consume", "topic": "device.${device_id}.${app}.hp.fifo", "save": "msg" }
      ],
      "transitions": [
        { "if": "@msg != None && @msg != 'pending'", "go_to": "send" },
        { "go_to": "wait" }
      ]
    },
    "send": {
      "actions": [
        { "do": "chat.focus_contact", "name": "@msg['contact_name']" },
        { "do": "wait_ms", "value": 200 },
        { "do": "chat.send_text", "text": "@msg['reply_text']" },
        { "do": "mq.ack", "topic": "device.${device_id}.${app}.hp.fifo", "from_var": "msg" }
      ],
      "transitions": [ { "go_to": "wait" } ]
    }
  }
}
```

> 在 Runner 载入工作流前，用简单的占位替换把 `${device_id}`、`${app}` 替换成真实值（或在动作里动态拼接 topic）。

---

# 7.D 云端 Worker（阶段 4）对接 device\_id

在 `server/worker.js` 里，把投递 HP 队列改为：
`device.<device_id>.<app>.hp.fifo`，`app` 从 `job` 或 `inputs` 中传（默认 `wechat`）。
（你在 `llm.submit` 中新增 `app` 字段或由云端推断。）

```js
// 简化示例
const app = body.inputs?.app || "wechat";
const device = body.device_target; // 即 device_id
const qname = `device.${device}.${app}.hp.fifo`;
```

---

# 7.E 如何运行（本地）

1. **起 Postgres + API**

   ```
   docker compose -f docker-compose.stage7.yml up -d
   curl http://localhost:8080/healthz   # {"ok":true}
   ```

   可用 `/auth/register` 新建用户，或用 init.sql 写的 demo 账号。

2. **客户端启动（自动弹登录窗）**

   * 设置 `API_BASE=http://localhost:8080`（你可以在 `run_stage7_demo.py` 里写死）
   * 启动：

     ```
     python scripts/run_stage7_demo.py
     ```
   * 登录 `demo@acme.com` / `demo123`（你若换了，就用自己的）

3. **观察注册流程**

   * 首次启动会在 `~/.autoagent/device.json` 生成 machine\_code
   * API 返回 `device_id`，日志打印：`registered device_id=...`
   * LocalStack（前几阶段）仍在运行；SQS 队列使用 `device.<device_id>.<app>.hp.fifo`

4. **跑 LP/HP**（沿用阶段 5、6 的工作流，改为 stage7 版本）

   * 看到 HP 抢占、自动回复；API 日志出现设备心跳与注册记录。

---

# 7.F 验收标准

* **必须登录**才能运行；未登录禁止创建工作流运行。
* 首次登录生成**machine\_code**并注册，服务器返回**device\_id**；再次启动复用同一 device。
* 超过订阅**设备上限**时，`/devices/register` 返回 `{error:"device limit reached"}`，客户端停止执行并提示。
* **所有数据与权限**都通过 **API** 访问；客户端无 Postgres 连接。
* HP/LP 及 CONTROL 队列名全部基于 **device\_id**，与之前阶段完整兼容。

---

# 7.G 风险与兜底

* **JWT 过期**：当前示例 8h，有需要可加 `/auth/refresh` 与自动刷新逻辑；短期可重新登录。
* **设备重装系统**：machine\_code 默认 UUIDv4 存文件；如果丢失会生成新设备并占用额度——后端可提供“解绑设备”功能。
* **同机多实例**：同一 machine\_code 可被多进程共享；如需隔离，可加入 `instance_id` 概念。
* **SQS 队列不存在**：在 `bootstrap_sqs.py` 增加基于 `device_id` 的动态创建（或 Worker/客户端检测创建）。
* **安全**：生产请使用 HTTPS、JWT 强密钥、密码策略与速率限制；管理员端可冻结设备（`devices.status=0`）。

---

做到这里，**阶段 7** 完成：账号→登录→设备注册→计划校验→队列命名与运行一体化。
阶段8:

阶段 8｜多 LLM 路由 + 用户 API Key（可不加密 & 管理后台可见）\*\*重新落地一版，满足你“允许明文存储 + 后台可查看”的需求，同时给出最小但必要的安全与审计措施，确保上线可控、可追溯。

---

# 8’ 目标变更（与原阶段 8 的差异）

* **API Key 存储支持两种模式**：`PLAINTEXT`（明文）与 `ENCRYPTED`（AES-GCM，后续可换 KMS），**同库共存**，可按用户/环境切换。
* **管理后台/管理 API 支持“查看/揭示”Key 明文**（含解密或直接读取明文），带**严格 RBAC + 二次验证 + 审计日志**。
* Worker 改造为**优先使用明文 key**，没有明文时再解密获取。
* 其余（路由、计量、限流、幂等）维持上一版。

---

# 1. 数据库变更（兼容原有表）

在上一版 `user_api_keys` 基础上，新增模式字段与明文列：

```sql
-- 迁移脚本：server/sql/llm_08_plaintext.sql
alter table user_api_keys
  add column if not exists mode text not null default 'ENCRYPTED',   -- 'PLAINTEXT' | 'ENCRYPTED'
  add column if not exists plaintext_key text,                       -- 明文可为空（仅 PLAINTEXT 填）
  add column if not exists created_by uuid,                          -- 操作人（管理员或用户）
  add column if not exists updated_at timestamptz;

-- 审计：谁、何时、为何查看/导出过明文
create table if not exists admin_secret_audit (
  id uuid primary key default uuid_generate_v4(),
  admin_user_id uuid references users(id),
  action text not null,                       -- 'REVEAL' | 'EXPORT' | 'LIST_REVEAL'
  target_table text not null default 'user_api_keys',
  target_id uuid not null,                    -- 对应的 key id
  reason text,
  ip text,
  ua text,
  created_at timestamptz default now()
);

-- RBAC（最小可用）
alter table users add column if not exists role text not null default 'user'; -- 'user' | 'admin'
```

> 说明
>
> * 老数据默认 `mode='ENCRYPTED'`，继续按旧逻辑工作。
> * 你可以针对**开发/内网**用户创建 `PLAINTEXT` 模式的 key，便于后台直接查看。

---

# 2. 服务器端 API 改造

## 2.1 Key 管理（用户侧 + 管理侧）

```js
// server/src/llm.js（在上一版基础上修改）
llm.post("/keys", authRequired, async (req, res) => {
  const { provider, name, api_key, mode } = req.body || {};
  if (!provider || !api_key) return res.status(400).json({ error: "bad params" });
  const m = (mode || process.env.DEFAULT_KEY_MODE || "ENCRYPTED").toUpperCase();

  let cols, vals, returning = "id,last4,provider,name,mode";
  const last4 = api_key.slice(-4);

  if (m === "PLAINTEXT") {
    cols = "user_id,provider,name,mode,plaintext_key,last4,created_by";
    vals = [req.user.user_id, provider, name || null, "PLAINTEXT", api_key, last4, req.user.user_id];
  } else {
    const { enc, iv, tag } = encryptKey(api_key);
    // base64 存储，便于可读备份（或直接 bytea）
    cols = "user_id,provider,name,mode,enc_key,iv,tag,last4,created_by";
    vals = [req.user.user_id, provider, name || null, "ENCRYPTED",
            enc.toString("base64"), iv.toString("base64"), tag.toString("base64"), last4, req.user.user_id];
  }

  const { rows } = await pool.query(
    `insert into user_api_keys(${cols}) values(${vals.map((_,i)=>'$'+(i+1)).join(',')})
     returning ${returning}`
  , vals);

  res.json({ key: rows[0] });
});

llm.get("/keys", authRequired, async (req, res) => {
  // 用户自己看：永远 **不返回明文**，仅 last4 与元信息
  const { rows } = await pool.query(
    "select id,provider,name,last4,mode,created_at from user_api_keys where user_id=$1 order by created_at desc",
    [req.user.user_id]
  );
  res.json({ keys: rows });
});
```

### 管理侧：可查看/揭示明文

```js
// server/src/admin_keys.js
import express from "express";
import { pool } from "./db.js";
import { authRequired } from "./middleware.js";
import { decryptKey } from "./crypto.js";

export const adminKeys = express.Router();

// 简单 RBAC：仅 admin 角色可用
function adminOnly(req, res, next){
  if (req.user?.role !== "admin") return res.status(403).json({ error: "forbidden" });
  next();
}

// 列表（不自动揭示）
adminKeys.get("/keys", authRequired, adminOnly, async (req, res) => {
  const { user_id } = req.query; // 可选过滤
  const q = user_id
    ? pool.query("select id,user_id,provider,name,mode,last4,created_at from user_api_keys where user_id=$1", [user_id])
    : pool.query("select id,user_id,provider,name,mode,last4,created_at from user_api_keys order by created_at desc limit 200");
  const { rows } = await q;
  res.json({ keys: rows });
});

// 揭示明文（需要 reason；可叠加一次性 OTP）
adminKeys.post("/keys/:id/reveal", authRequired, adminOnly, async (req, res) => {
  const { reason, otp } = req.body || {};
  if (!reason) return res.status(400).json({ error: "reason_required" });
  // TODO: verify OTP（若开启）
  const { rows } = await pool.query("select * from user_api_keys where id=$1", [req.params.id]);
  if (!rows.length) return res.status(404).json({ error: "not_found" });
  const k = rows[0];

  let plain = null;
  if (k.mode === "PLAINTEXT") {
    plain = k.plaintext_key;
  } else {
    plain = decryptKey(Buffer.from(k.enc_key, "base64"), Buffer.from(k.iv, "base64"), Buffer.from(k.tag, "base64"));
  }

  // 审计
  await pool.query(
    "insert into admin_secret_audit(admin_user_id,action,target_id,reason,ip,ua) values($1,'REVEAL',$2,$3,$4,$5)",
    [req.user.user_id, k.id, reason, req.ip, req.headers['user-agent'] || ""]
  );

  res.json({ id: k.id, provider: k.provider, name: k.name, mode: k.mode, api_key: plain });
});
```

> 默认**用户接口**仍不返回明文，只有**管理员接口**在提供“揭示”能力。

---

# 3. Worker 改造（优先走明文）

```js
// server/router_db.js（替换 findKeyForProvider）
export function findKeyForProvider(keys, provider){
  const k = keys.find(x => x.provider.toLowerCase() === provider.toLowerCase());
  if (!k) return null;
  if (k.mode === "PLAINTEXT" && k.plaintext_key) {
    return { apiKey: k.plaintext_key, last4: k.last4, mode: "PLAINTEXT" };
  }
  // 兼容加密
  if (k.enc_key && k.iv && k.tag) {
    const apiKey = decryptKey(Buffer.from(k.enc_key, "base64"), Buffer.from(k.iv, "base64"), Buffer.from(k.tag, "base64"));
    return { apiKey, last4: k.last4, mode: "ENCRYPTED" };
  }
  return null;
}
```

> 其余路由、计量逻辑不变。

---

# 4. 配置与部署建议（支持**按环境开关**）

* `.env`

  * `DEFAULT_KEY_MODE=PLAINTEXT`（开发/内网）或 `ENCRYPTED`（生产）
  * `ALLOW_ADMIN_REVEAL=1`（生产也可开，但强制审计/OTP）
  * `MASTER_KEY_HEX=...`（若使用 ENCRYPTED）
* 管理后台（前端或简单 API）：

  * “Key 列表”页默认只显示 `last4`；
  * “点击揭示”弹窗要求输入**揭示原因**（必填）与**一次性验证码**（可与管理员个人 2FA 绑定）；
  * 每次揭示都写 `admin_secret_audit`，列表可导出。

---

# 5. 最小安全与合规措施（即使明文也要做的底线）

1. **最小权限**：仅 `admin` 角色能调用 `/admin/keys/:id/reveal`；普通用户只能管理自己的 key（看不到明文）。
2. **审计不可篡改**：`admin_secret_audit` 表只插入不更新，管理员前端显示揭示次数与最近一次揭示人/时间/原因。
3. **日志与监控**：所有 API 层**严禁**把 `api_key` 打进日志；Nginx/反代也要过滤 query/body 中的 `api_key` 字段。
4. **导出与下载**：如果提供“批量导出”，同样走审计；默认关闭批量导出。
5. **网络与 IP 白名单**：管理后台可限制只允许公司内网/特定 VPN 网段访问。
6. **速率限制**：对 `/admin/keys/:id/reveal` 做极低 QPS（如 5/min per admin），防止爆破或爬取。
7. **事故应急**：支持**一键转密**：把某用户或所有 `PLAINTEXT` Key 迁移到 `ENCRYPTED`，并清空 `plaintext_key`。

---

# 6. 客户端影响

* **无变更**：客户端既不上传/查看明文（除创建时带上），也不直连数据库。
* 仍旧用 `llm.submit` 提交任务，Worker 在服务器侧完成路由与 Key 取用。

---

# 7. 运行与验收（本地）

1. 跑数据库迁移：`llm_08_plaintext.sql`。
2. 启动 API + Worker（沿用阶段 8）。
3. 用户调用 `POST /llm/keys`：

   * `{"provider":"openai","mode":"PLAINTEXT","api_key":"sk-xxx"}`
   * `GET /llm/keys` 仅见 meta+last4。
4. 管理员登录（`users.role='admin'`）：

   * `GET /admin/keys?user_id=<uid>` 列表
   * `POST /admin/keys/:id/reveal {reason:"调试路由"}` → 返回明文/解密明文，并在 `admin_secret_audit` 生成记录
5. 执行一次 LLM 任务：Worker 读取明文/解密 Key，成功路由，`llm_jobs/llm_usage` 纪录正常。

**通过标准**

* 管理员能按需**揭示**用户 key（或解密后明文），且每次都有审计。
* 普通用户**永远**看不到明文。
* Worker 优先用明文，无明文再解密。
* 关闭加密时（全 PLAINTEXT），系统仍安全可控：RBAC + 审计 + 限流 + 后台访问控制。

---

# 8. 风险与注意（我必须直说）

* **明文存储 = 更高风险**：一旦数据库被读取，Key 立即失守。请至少采用：

  * 管理后台只在内网/VPN；
  * 数据库磁盘加密（云盘默认通常支持）；
  * 定期轮换 key（后台可提供“轮换”按钮 → Worker 热更新）。
* **合规**：如果后续面向企业客户，强烈建议把默认模式切回 `ENCRYPTED`，只对少数管理员开放“揭示解密后的明文”。

---

# 9. 迁移/回滚

* 从旧版（强制加密）升级：无缝；`mode` 默认为 `ENCRYPTED`。
* 想把明文 Key 批量改回加密：

  1. 遍历 `PLAINTEXT`，对 `plaintext_key` 调 `encryptKey`，写 `enc_key/iv/tag`；
  2. 置 `mode='ENCRYPTED'` 并清空 `plaintext_key`；
  3. 记录一次“批量转密”的审计。


允许明文 API Key + 管理后台可见\*\*的“管理小前端（React）+ 一套可直接跑的 cURL 脚本”

---

# 一、服务端微更新（确保路由挂载）

在你的 `server/src/index.js` 里**挂上管理员 key 路由**（上一轮我给了 `admin_keys.js`）：

```js
import { adminKeys } from "./admin_keys.js";
// ...
app.use("/admin", adminKeys);   // 新增
```

> 你已全局 `app.use(cors())`，开发期前端直连没问题；生产记得把 CORS 域收紧。

可选：`.env`

```
DEFAULT_KEY_MODE=PLAINTEXT   # 开发/内网默认走明文；生产建议 ENCRYPTED
ALLOW_ADMIN_REVEAL=1         # 若以后要做后端开关，可读取此变量
```

---

# 二、管理员小前端（React，Vite，极简而专业）

目录（任意新建 `admin-ui/`）：

```
admin-ui/
├─ package.json
├─ index.html
├─ src/
│  ├─ main.jsx
│  └─ App.jsx
└─ vite.config.js   (可选)
```

## 1) package.json

```json
{
  "name": "admin-key-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview --port 5174"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "vite": "^5.4.0"
  }
}
```

## 2) vite.config.js（可选，保持默认即可）

```js
export default {
  server: { port: 5173 }
};
```

## 3) index.html

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Admin Key Console</title>
    <style>
      :root { --bg:#0b0f17; --card:#121826; --muted:#9aa4b2; --txt:#e6edf3; --acc:#4f9cff; }
      body{margin:0;font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,Helvetica,Arial;
           background:linear-gradient(180deg,#0b0f17,#0e1422 40%,#0b0f17);}
      .wrap{max-width:980px;margin:40px auto;padding:0 16px;color:var(--txt);}
      .card{background:var(--card); border:1px solid #1f2937; border-radius:16px; padding:20px; box-shadow:0 8px 24px rgba(0,0,0,.25);}
      .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:8px 0}
      input,select,button,textarea{
        background:#0b1220; color:var(--txt); border:1px solid #263041; border-radius:10px; padding:10px 12px; outline:none;
      }
      button{cursor:pointer}
      table{width:100%; border-collapse:collapse; margin-top:10px}
      th,td{padding:10px 8px; border-bottom:1px solid #233044; color:#d7dee8}
      .muted{color:var(--muted)}
      .pill{background:#0d1b2a;border:1px solid #1e2a3b;padding:3px 8px;border-radius:999px;font-size:12px}
      .danger{background:#2a0d0d; border-color:#3b1e1e}
      .success{background:#0d2a15; border-color:#1e3b27}
      .acc{color:var(--acc)}
      .grid{display:grid; grid-template-columns:1fr 1fr; gap:12px}
      @media (max-width:720px){ .grid{grid-template-columns:1fr} }
      .kbd{font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; padding:2px 6px; background:#0b1220; border:1px solid #223045; border-radius:6px}
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

## 4) src/main.jsx

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(<App />);
```

## 5) src/App.jsx

```jsx
import React, { useEffect, useMemo, useState } from "react";

const load = (k, d="") => localStorage.getItem(k) ?? d;
const save = (k, v) => localStorage.setItem(k, v);

export default function App(){
  const [apiBase, setApiBase] = useState(load("apiBase", "http://localhost:8080"));
  const [token, setToken] = useState(load("adminJwt", ""));
  const [userId, setUserId] = useState(load("filterUserId", ""));
  const [keys, setKeys] = useState([]);
  const [reveal, setReveal] = useState(null); // {id, provider, name, last4}
  const [reason, setReason] = useState("");
  const [otp, setOtp] = useState("");

  useEffect(()=>{ save("apiBase", apiBase); }, [apiBase]);
  useEffect(()=>{ save("adminJwt", token); }, [token]);
  useEffect(()=>{ save("filterUserId", userId); }, [userId]);

  const headers = useMemo(()=>({
    "Authorization": token ? `Bearer ${token}` : "",
    "Content-Type":"application/json"
  }), [token]);

  async function fetchKeys(){
    if(!apiBase || !token){ alert("请先填 API Base 与 Admin JWT"); return; }
    const url = userId ? `${apiBase}/admin/keys?user_id=${encodeURIComponent(userId)}` : `${apiBase}/admin/keys`;
    const r = await fetch(url, { headers });
    if(!r.ok){ alert("获取失败：" + r.status); return; }
    const j = await r.json();
    setKeys(j.keys || []);
  }

  async function doReveal(id){
    if(!reason.trim()){ alert("请填写揭示原因"); return; }
    const r = await fetch(`${apiBase}/admin/keys/${id}/reveal`, {
      method:"POST", headers,
      body: JSON.stringify({ reason, otp: otp || undefined })
    });
    if(!r.ok){ alert("揭示失败：" + r.status); return; }
    const j = await r.json();
    setReveal({ ...reveal, plain: j.api_key });
  }

  function copy(txt){
    navigator.clipboard?.writeText(txt);
  }

  return (
    <div className="wrap">
      <h2 style={{letterSpacing:.2+'px'}}>Admin Key Console <span className="muted">（明文/解密揭示）</span></h2>
      <div className="card">
        <div className="row">
          <div className="grid" style={{width:"100%"}}>
            <div>
              <div className="muted">API Base</div>
              <input value={apiBase} onChange={e=>setApiBase(e.target.value)} placeholder="http://localhost:8080" style={{width:"100%"}}/>
            </div>
            <div>
              <div className="muted">Admin JWT</div>
              <input value={token} onChange={e=>setToken(e.target.value)} placeholder="粘贴管理员登录后获得的 JWT" style={{width:"100%"}}/>
            </div>
          </div>
        </div>
        <div className="row">
          <input value={userId} onChange={e=>setUserId(e.target.value)} placeholder="按用户ID过滤（可空）" style={{flex:1}}/>
          <button onClick={fetchKeys}>拉取 Keys</button>
        </div>

        <table>
          <thead>
            <tr>
              <th style={{textAlign:'left'}}>Key ID</th>
              <th>用户</th>
              <th>Provider</th>
              <th>名称</th>
              <th>模式</th>
              <th>Last4</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
          {keys.map(k=>(
            <tr key={k.id}>
              <td className="kbd">{k.id}</td>
              <td className="kbd">{k.user_id}</td>
              <td>{k.provider}</td>
              <td>{k.name || <span className="muted">-</span>}</td>
              <td><span className="pill">{k.mode}</span></td>
              <td className="kbd">{k.last4}</td>
              <td>
                <button onClick={()=>{ setReveal(k); setReason(""); setOtp(""); }}>揭示</button>
              </td>
            </tr>
          ))}
          {!keys.length && <tr><td colSpan="7" className="muted">暂无数据</td></tr>}
          </tbody>
        </table>
      </div>

      {reveal && (
        <div style={{position:'fixed', inset:0, background:'rgba(0,0,0,.5)', display:'grid', placeItems:'center'}}>
          <div className="card" style={{width:'min(680px, 96vw)'}}>
            <div className="row" style={{justifyContent:'space-between'}}>
              <div>
                <div className="muted">揭示 Key（强审计）</div>
                <div><b>{reveal.provider}</b> / <span className="muted">{reveal.name || '-'}</span> / <span className="kbd">{reveal.id}</span></div>
              </div>
              <button onClick={()=>setReveal(null)}>关闭</button>
            </div>
            <div className="row">
              <textarea placeholder="填写揭示原因（必填）" value={reason} onChange={e=>setReason(e.target.value)} style={{width:'100%',minHeight:80}}/>
            </div>
            <div className="row">
              <input placeholder="OTP（如启用二次验证）" value={otp} onChange={e=>setOtp(e.target.value)} style={{flex:1}}/>
              <button className="danger" onClick={()=>doReveal(reveal.id)}>确认揭示</button>
            </div>
            {reveal.plain && (
              <div className="row">
                <div className="muted">明文：</div>
                <div className="kbd" style={{wordBreak:'break-all'}}>{reveal.plain}</div>
                <button onClick={()=>copy(reveal.plain)}>复制</button>
              </div>
            )}
            {!reveal.plain && <div className="muted">提交后返回明文；每次揭示都会记录审计日志。</div>}
          </div>
        </div>
      )}

      <p className="muted" style={{marginTop:12}}>
        小贴士：JWT 请用 <span className="kbd">admin</span> 角色登录获取；生产建议只在 VPN/内网开放本页面。
      </p>
    </div>
  );
}
```

### 启动

```bash
cd admin-ui
npm i
npm run dev
# 浏览器打开 http://localhost:5173
# 填 API Base（如 http://localhost:8080）和管理员 JWT，点“拉取 Keys”，然后“揭示”
```

> 管理员 JWT：用你的后台登录接口拿（阶段 7 的 `/auth/login`），并确保该账号 `users.role='admin'`。

---

# 三、cURL / Postman 脚本（开箱即用）

把下面保存为 `scripts/stage8_plaintext_key.sh`（记得 `chmod +x`），或直接逐条粘贴：

```bash
#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8080}"
USER_TOKEN="${USER_TOKEN:-}"     # 普通用户 JWT（创建自己 key 用）
ADMIN_TOKEN="${ADMIN_TOKEN:-}"   # 管理员 JWT（揭示用）

json() { jq -r "$1"; }

echo "1) 用户侧：创建 PLAINTEXT Key（OpenAI）"
resp=$(curl -sS -X POST "$API_BASE/llm/keys" \
  -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"openai","name":"default","mode":"PLAINTEXT","api_key":"sk-your-test-key-xxxx"}')
echo "$resp" | jq
KEY_ID=$(echo "$resp" | json '.key.id')

echo "2) 用户侧：列出自己的 keys（不含明文）"
curl -sS "$API_BASE/llm/keys" -H "Authorization: Bearer $USER_TOKEN" | jq

echo "3) 管理侧：列出所有 keys（meta）"
curl -sS "$API_BASE/admin/keys" -H "Authorization: Bearer $ADMIN_TOKEN" | jq

echo "4) 管理侧：揭示明文（审计）"
curl -sS -X POST "$API_BASE/admin/keys/$KEY_ID/reveal" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"reason":"路由联调","otp":""}' | jq

echo "5) （可选）上传 Prompt Pack 与 Schema"
curl -sS -X POST "$API_BASE/llm/prompt_packs" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"key":"wechat.sales.reply.v1","revision":1,"content":"你是销售助手。输出 JSON：{{inputs_json}}"}' | jq

curl -sS -X POST "$API_BASE/llm/schemas" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"key":"WeChatReplyV1","revision":1,"schema":{"type":"object","required":["contact_name","reply_text"],"properties":{"contact_name":{"type":"string"},"reply_text":{"type":"string"}}}}' | jq

echo "6) 路由策略（强制 openai）"
curl -sS -X POST "$API_BASE/llm/policies" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"job":"chat_reply","strategy":"FORCE:openai"}' | jq

echo "完成。现在客户端用 llm.submit -> Worker 会读取明文 Key 路由。"
```

> 环境变量：
>
> * `API_BASE=http://localhost:8080`
> * `USER_TOKEN=` 和 `ADMIN_TOKEN=` 需要先用 `/auth/login` 拿到（用户和管理员各一份）
> * 要是你用 Postman，照着这些路径/请求体建就可以了。

---

# 四、注意与最佳实践（在“可看明文”的前提下把风险降到最低）

* 管理端**仅 admin 角色**可揭示；每次揭示**必须写审计**（我已在路由里做了）。
* 生产只在 **VPN/内网**部署这个页面，或在 API 层对 `/admin/keys*` 做 IP 白名单与严格限速。
* 日志里**禁止输出**任何 `api_key` 字段（包括 Nginx 反代 access log 的 query/body）。
* 提供\*\*“一键转密”\*\*脚本（后续要回到 ENCRYPTED 时，把 `PLAINTEXT` 批量加密并清空明文列）。
* 定期轮转 key：在管理页面加个“替换 Key”动作（创建新 Key 并作废旧 Key）。

---

这样你就有：

* 一个**可直接运行**的 React 管理小前端（拉取 / 揭示 API Key，带理由输入与审计）；
* 一套 **cURL 脚本**，一键完成“创建明文 Key → 管理员揭示 → 上传 Prompt/Schema → 设置路由策略”。


阶段9:
阶段 9｜结算与账单（订阅 + 用量计费 + 多渠道支付）**。这一阶段把你前面第 7/8 阶段的“登录 / 设备注册 / 多 LLM 路由 + 计量”真正对齐到**可收费**状态：用户能购买订阅、充值钱包、按 LLM 用量出账、逾期限流、发票可查，且**客户端始终只走 API**（不直连 PG）。

---

# 9.A 目标（落地后具备）

* **订阅计费**（按月/年）：控制 *device\_limit / hp\_concurrency / 市场 workflow 授权数*。
* **用量计费**（usage-based）：按 `llm_usage` 汇总，写入账单（可与订阅合并开票）。
* **支付通道**：首选 **Stripe**（支持信用卡、Alipay、WeChatPay*在部分地区*），可抽象出 **支付提供商适配层**（未来接 native 微信/支付宝）。
* **预付钱包**（可选）：余额冲抵用量费；余额不足时进入“软限/硬限”。
* **阈值预警 & 催缴**：邮件/站内通知；逾期自动降级或限流。
* **对账可靠性**：Webhook 签名校验、全链路幂等、SQS 事件驱动、发票与支付流水可追溯。

---

# 9.B 数据模型（Postgres，仅**服务器**访问）

> 在 `server/sql/llm.sql` 基础上新增以下对象（可以作为 `20-billing.sql`）：

```sql
-- 价格与产品（可映射到 Stripe 上的 product/price）
create table plan_products (
  id uuid primary key default uuid_generate_v4(),
  key text unique not null,                 -- 'pro', 'team'
  name text not null,
  description text,
  device_limit int not null,
  hp_concurrency int not null,
  monthly_price_usd numeric(12,2) not null,
  yearly_price_usd numeric(12,2) not null,
  metadata jsonb default '{}'::jsonb
);

-- 订阅（与阶段7的 subscriptions 可合并/扩展）
alter table subscriptions add column external_sub_id text; -- stripe subscription id
alter table subscriptions add column currency text default 'usd';
alter table subscriptions add column billing_cycle_start timestamptz;
alter table subscriptions add column billing_cycle_end timestamptz;

-- 钱包（可选）
create table wallets (
  user_id uuid primary key references users(id),
  balance_cents bigint not null default 0,  -- 以分计价，避免浮点
  currency text not null default 'usd',
  updated_at timestamptz default now()
);

create table wallet_txns (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  type text not null,                        -- 'topup' | 'debit' | 'refund' ...
  amount_cents bigint not null,
  currency text not null default 'usd',
  ref text,                                  -- 对应的invoice/payment id等
  created_at timestamptz default now()
);

-- 发票与行
create table invoices (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  period_start timestamptz not null,
  period_end timestamptz not null,
  currency text not null default 'usd',
  subtotal_cents bigint not null default 0,
  tax_cents bigint not null default 0,
  total_cents bigint not null default 0,
  status text not null default 'draft',      -- draft|open|paid|void|uncollectible
  external_invoice_id text,                  -- stripe invoice id
  created_at timestamptz default now(),
  finalized_at timestamptz,
  paid_at timestamptz
);

create table invoice_lines (
  id uuid primary key default uuid_generate_v4(),
  invoice_id uuid references invoices(id) on delete cascade,
  kind text not null,                        -- 'subscription' | 'usage' | 'marketplace' | 'credit'
  description text,
  quantity int,
  unit_amount_cents bigint,                  -- 单价（分）
  amount_cents bigint not null,              -- 行金额（分）
  meta jsonb default '{}'::jsonb
);

-- 用量聚合（由 llm_usage 汇总写入）
create table usage_rollups (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  period_start timestamptz not null,
  period_end timestamptz not null,
  provider text not null,
  model text not null,
  prompt_tokens bigint not null,
  completion_tokens bigint not null,
  amount_cents bigint not null,
  currency text not null default 'usd',
  created_at timestamptz default now(),
  unique(user_id, period_start, period_end, provider, model)
);

-- 支付流水
create table payments (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  invoice_id uuid references invoices(id),
  provider text not null,                    -- stripe|wxpay|alipay...
  external_payment_id text,
  currency text not null default 'usd',
  amount_cents bigint not null,
  status text not null,                      -- succeeded|failed|pending|refunded
  created_at timestamptz default now()
);

-- 发票阈值/信用限额
create table billing_limits (
  user_id uuid primary key references users(id),
  soft_cap_cents bigint not null default 1000,  -- 超过发提醒
  hard_cap_cents bigint not null default 2000   -- 超过限流/停止
);

-- 市场 workflow 购买与授权（预留给阶段10）
create table marketplace_entitlements (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  workflow_key text not null,
  seats int not null default 1,
  expires_at timestamptz,
  created_at timestamptz default now(),
  unique(user_id, workflow_key)
);
```

---

# 9.C 支付提供商适配层（Server）

> 新增 `server/src/payments/`：统一接口 `createCheckoutSession`, `handleWebhook`, `createPortalSession`。

```
server/src/payments/
├─ index.js                 # 工厂 + 统一导出
├─ stripe.js                # Stripe 实现（test mode）
├─ alipay.js                # 占位：需接国内通道时实现
├─ wxpay.js                 # 占位：同上
```

示例（Stripe）：

```js
// server/src/payments/stripe.js
import Stripe from "stripe";
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, { apiVersion: "2024-06-20" });

export async function createCheckoutSession({ user, plan, mode="subscription", success_url, cancel_url }) {
  // 预先在 Stripe 上创建 products/prices，对应 plan_products
  // 这里假设 price_id 已在 env 或 DB 里映射
  const priceId = plan === "pro" ? process.env.STRIPE_PRICE_PRO_MONTHLY : process.env.STRIPE_PRICE_TEAM_MONTHLY;

  const customer = await ensureCustomer(user);
  const session = await stripe.checkout.sessions.create({
    mode,
    customer,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url, cancel_url,
    payment_method_types: ["card", "alipay", "wechat_pay"].filter(Boolean) // 可按地区开关
  });
  return { id: session.id, url: session.url };
}

export async function createPortalSession({ user, return_url }) {
  const customer = await ensureCustomer(user);
  const portal = await stripe.billingPortal.sessions.create({ customer, return_url });
  return { url: portal.url };
}

export function verifyWebhook(rawBody, sig) {
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;
  return stripe.webhooks.constructEvent(rawBody, sig, endpointSecret);
}

async function ensureCustomer(user){
  if (user.stripe_customer_id) return user.stripe_customer_id;
  const c = await stripe.customers.create({ email: user.email, metadata: { user_id: user.id } });
  // 写回 PG 略
  return c.id;
}
```

---

# 9.D 服务端 API（Billing 路由）

新增 `server/src/billing.js`：

```js
import express from "express";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import * as StripePay from "./payments/stripe.js";

export const billing = express.Router();

// 1) 订阅购买：返回 Checkout URL
billing.post("/checkout", authRequired, async (req, res) => {
  const { plan_key, mode } = req.body || {};
  const plan = await pool.query("select * from plan_products where key=$1", [plan_key]);
  if (!plan.rowCount) return res.status(400).json({ error: "bad plan" });

  const user = await pool.query("select id,email from users where id=$1", [req.user.user_id]).then(r=>r.rows[0]);
  const urls = {
    success_url: process.env.APP_URL + "/billing/success",
    cancel_url: process.env.APP_URL + "/billing/cancel"
  };
  const { url } = await StripePay.createCheckoutSession({ user, plan: plan_key, mode: mode || "subscription", ...urls });
  res.json({ url });
});

// 2) 客户门户（修改卡片 / 取消订阅）
billing.post("/portal", authRequired, async (req, res) => {
  const user = await pool.query("select id,email,stripe_customer_id from users where id=$1",[req.user.user_id]).then(r=>r.rows[0]);
  const { url } = await StripePay.createPortalSession({ user, return_url: process.env.APP_URL + "/app" });
  res.json({ url });
});

// 3) 发票查询
billing.get("/invoices", authRequired, async (req, res) => {
  const { rows } = await pool.query("select * from invoices where user_id=$1 order by created_at desc limit 50", [req.user.user_id]);
  res.json({ invoices: rows });
});
```

Webhook（`server/src/webhooks.js`）：

```js
import express from "express";
import { verifyWebhook } from "./payments/stripe.js";
import { pool } from "./db.js";

export const webhooks = express.Router();

webhooks.post("/stripe", express.raw({ type: "application/json" }), async (req, res) => {
  let evt;
  try { evt = verifyWebhook(req.body, req.headers['stripe-signature']); }
  catch(e){ return res.status(400).send(`Webhook Error: ${e.message}`); }

  switch (evt.type) {
    case "checkout.session.completed": {
      // 创建/更新订阅，写 subscriptions.external_sub_id，设置周期起止
      break;
    }
    case "invoice.payment_succeeded": {
      // 找到对应 invoices.external_invoice_id，置 paid_at/status='paid'
      break;
    }
    case "invoice.payment_failed": {
      // dunning：标记 open/uncollectible，触发限流
      break;
    }
    case "customer.subscription.updated":
    case "customer.subscription.deleted": {
      // 同步订阅状态与 plan
      break;
    }
  }
  res.json({ received: true });
});
```

> 生产务必做：**签名校验**、**幂等处理**（`Idempotency-Key` / 事件 id 去重）。

在 `server/src/index.js` 里挂载：

```js
import { billing } from "./billing.js";
import { webhooks } from "./webhooks.js";
app.use("/billing", billing);
app.use("/webhooks", webhooks);  // 注意：webhook 采用 raw body，不要被全局 json 中间件吞掉
```

---

# 9.E 用量聚合与开票（Billing Worker）

> 独立进程（或 cron job），从 `llm_usage` 汇总到 `usage_rollups`，然后生成/更新当期 `invoices` 与 `invoice_lines`。

```
server/workers/billing_aggregator.js
```

核心逻辑（伪码）：

```js
import { pool } from "../src/db.js";
import dayjs from "dayjs";

async function rollupPeriod(user_id, start, end){
  const q = `
    select provider, model,
           sum(prompt_tokens) as p, sum(completion_tokens) as c
    from llm_usage
    where user_id=$1 and ts >= $2 and ts < $3
    group by provider, model`;
  const { rows } = await pool.query(q, [user_id, start, end]);

  for (const r of rows) {
    // 将 token → 金额（分）：可重用阶段8的定价逻辑（在 server/pricing.js 中）
    const cents = await tokensToCents(r.provider, r.model, r.p, r.c, "usd");
    await pool.query(`
      insert into usage_rollups(user_id,period_start,period_end,provider,model,prompt_tokens,completion_tokens,amount_cents)
      values($1,$2,$3,$4,$5,$6,$7,$8)
      on conflict(user_id,period_start,period_end,provider,model)
      do update set prompt_tokens=$6, completion_tokens=$7, amount_cents=$8
    `, [user_id, start, end, r.provider, r.model, r.p, r.c, cents]);
  }
}

async function ensureOpenInvoice(user_id, start, end){
  const q = `select * from invoices where user_id=$1 and period_start=$2 and period_end=$3`;
  const { rows } = await pool.query(q, [user_id, start, end]);
  if (rows.length) return rows[0];
  const ins = await pool.query(
    `insert into invoices(user_id,period_start,period_end,status) values($1,$2,$3,'open') returning *`,
    [user_id, start, end]
  );
  return ins.rows[0];
}

async function upsertInvoiceLines(user_id, inv){
  // 订阅费
  const sub = await pool.query(`select s.plan, p.monthly_price_usd
    from subscriptions s join plan_products p on p.key=s.plan
    where s.user_id=$1 and s.status='active' limit 1`, [user_id]);
  if (sub.rowCount) {
    const priceCents = Math.round(Number(sub.rows[0].monthly_price_usd) * 100);
    await addLine(inv.id, 'subscription', `${sub.rows[0].plan} monthly`, 1, priceCents, priceCents);
  }
  // 用量费
  const rolls = await pool.query(`select provider,model,amount_cents from usage_rollups
    where user_id=$1 and period_start=$2 and period_end=$3`, [user_id, inv.period_start, inv.period_end]);
  for (const r of rolls.rows) {
    await addLine(inv.id, 'usage', `${r.provider}/${r.model}`, 1, r.amount_cents, r.amount_cents);
  }
  // 汇总
  await pool.query(`update invoices set subtotal_cents =
      (select coalesce(sum(amount_cents),0) from invoice_lines where invoice_id=$1),
      total_cents = (select coalesce(sum(amount_cents),0) from invoice_lines where invoice_id=$1)
    where id=$1`, [inv.id]);
}

async function addLine(invoice_id, kind, desc, qty, unit_cents, amount_cents){
  await pool.query(
    `insert into invoice_lines(invoice_id,kind,description,quantity,unit_amount_cents,amount_cents)
     values($1,$2,$3,$4,$5,$6)`,
    [invoice_id, kind, desc, qty, unit_cents, amount_cents]
  );
}

async function main(){
  // 对每个用户按其订阅周期开票（最简单：月对月）
  const users = await pool.query("select id from users where status=1");
  for (const u of users.rows) {
    const start = dayjs().startOf('month').toISOString();
    const end   = dayjs().endOf('month').add(1,'second').toISOString();
    await rollupPeriod(u.id, start, end);
    const inv = await ensureOpenInvoice(u.id, start, end);
    await upsertInvoiceLines(u.id, inv);
  }
  console.log("[billing] rollup done");
}

main().catch(e=>{ console.error(e); process.exit(1); });
```

> 生产中你会把这段拆成：**日滚汇总**（小时/日粒度）+ **月末 finalize** + **发 Stripe 发票**（或在 Stripe 侧做 metered 计费，二选一）。

---

# 9.F 限流与阈值（落到第 8 阶段 Router）

在 Worker 的路由阶段（第 8 阶段 `router_db.js`）加入**额度检查**：

* **钱包余额**（优先）≥ 预计本次调用最高费用（按上限估算），放行；否则走订阅额度。
* **账期内累计 `invoices.total_cents(open)` + 已发生用量** ≥ `hard_cap_cents` → 返回 `402 Payment Required`，并写 `llm_jobs` 失败。
* 触发 `soft_cap_cents` → 仍放行，但发一次预警（SQS 事件 + 邮件）。

示例（伪码）：

```js
// before callProvider(...)
const limits = await pool.query("select * from billing_limits where user_id=$1",[user_id]).then(r=>r.rows[0]||{});
const openInv = await pool.query("select coalesce(sum(total_cents),0) as s from invoices where user_id=$1 and status in ('open','draft')",[user_id]).then(r=>Number(r.rows[0].s)||0);

if (openInv >= limits.hard_cap_cents) throw Object.assign(new Error("HARD_LIMIT"), { code: "PAYMENT_REQUIRED" });
if (openInv >= limits.soft_cap_cents) emitAlertOnce(user_id, "SOFT_CAP_NEAR");
```

---

# 9.G 客户端改动（极少）

* 新增两条 API 调用：

  * `POST /billing/checkout` 返回 URL → **用系统浏览器打开**（桌面客户端里弹“去支付”按钮）；
  * `POST /billing/portal` 返回 URL → 打开管理页（变更卡、取消订阅、发票下载）。
* 在 UI 上展示三块：**当前订阅**（plan & device\_limit）、**本期已用金额**、**钱包余额**。
* 业务限制（HP 并发/设备上限）继续由**服务器**控制，客户端只读。

---

# 9.H 开发/联调步骤（本地）

1. **起服务**：在 `docker-compose.stage8.yml` 基础上再添加 `webhooks` 路由（API 已有），保持 DB/Redis/API/LocalStack/Worker 全部运行。
2. **Stripe**：使用 **测试密钥**（`.env` 设置 `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`、价格 id）。
3. **初始化 plan\_products**（插入 `pro/team` 两档）。
4. **调用 `/billing/checkout`** 获取 URL，浏览器里用**测试卡**支付（4242 4242 4242 4242 …）。
5. **观察 Webhook**：`checkout.session.completed` → `subscriptions` 更新；开具当期 `invoices`；`invoice.payment_succeeded` → 标记 paid。
6. **压测用量**：调用 LLM，生成 `llm_usage` → 跑 `billing_aggregator.js` → `invoices/invoice_lines` 自动补齐 usage 行。
7. **限流测试**：把 `billing_limits.hard_cap_cents` 设很低，再调用 LLM，应返回“额度用尽”，HP 不再回包（并记录失败）。

---

# 9.I 成功标准

* 用户能通过 **/billing/checkout** 成功开通订阅；**/billing/portal** 可管理订阅。
* 定时/手动 **汇总用量** → 发票中出现 **订阅行 + 用量行**；支付成功后发票置 **paid**。
* **软限**触发一次预警，**硬限**阻断 LLM 调用（第 8 阶段 Worker 返回 Payment Required）。
* **钱包**扣费/充值流水完整（若启用）。
* 客户端全程**不直连 PG**，所有动作均通过 API + SQS。

---

# 9.J 风险与兜底

* **地区支付**：Stripe 在国内卡 & 微信/支付宝可用性受限；适配层已预留 `alipay.js/wxpay.js`，后续可替换为原生通道（服务端接）。
* **税/VAT**：发票税务处理可先置 0；逐步引入 `tax_rates` 与用户 `billing_address`。
* **币种**：内部记账统一 USD 分，展示时用汇率换算（每日缓存）。
* **对账一致性**：Webhook 必做幂等，`event_id` 去重；发票状态只允许单向迁移。
* **计量延迟**：用量汇总采用 *近实时*（每 5 分钟）+ *T+1 修正*，避免漏计/多计。
* **滥用防护**：对免费试用设置更低 `hard_cap` 与 `hp_concurrency`；BYOK 用户可选“只用自己 Key，不计入平台账单”。


阶段10:

阶段 10｜Workflow 市场（上架/购买/授权/安装/更新）**。这一阶段做完，你就能：把成熟的自动化工作流“打包→签名→上架”，用户**付费购买**后获得授权，客户端**拉取并验证签名**后本地安装运行；授权按**用户/设备/席位**精确控制，**计费与订阅**与第 9 阶段无缝衔接。仍然遵守你的底线：**客户端只走 API，不直连 PG**。

---

# 10.A 目标与边界

* 市场最小可用：**上架 → 浏览 → 购买 → 授权 → 安装 → 更新** 全链路打通
* 包含**工作流签名与完整性校验**（ed25519），客户端只运行**签名有效**且**权限白名单通过**的包
* **授权模型**：按用户（可带设备 seat 数），支持过期/撤销/退款
* 与第 8/9 阶段联动：**结算/发票/限流**与用量计费合并展示
* 支持**多版本/回滚**与**自动更新**（可锁定版本）
* 服务端提供**发布者门户**（Publisher），支持**收益分账**（Stripe Connect）

---

# 10.B 数据模型（仅服务端访问）

> 基于你第 9 阶段已建的 `marketplace_entitlements`，补充如下（迁移脚本 `30-marketplace.sql`）：

```sql
-- 发布者与结算
create table publishers (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),           -- 拥有者
  name text not null,
  contact_email text,
  stripe_account_id text,                      -- Stripe Connect 账号
  status text not null default 'active'
);

-- 工作流清单（Listing）与版本
create table marketplace_listings (
  id uuid primary key default uuid_generate_v4(),
  publisher_id uuid references publishers(id),
  key text not null,                           -- 唯一，如 "xhs.crawler.v1"
  title text not null,
  summary text,
  category text,                               -- chat-automation / scraping / sales-assist ...
  price_cents bigint not null default 0,
  currency text not null default 'usd',
  visibility text not null default 'public',   -- public/private/unlisted
  latest_version text,                         -- "1.2.0"
  created_at timestamptz default now(),
  unique (publisher_id, key)
);

create table marketplace_versions (
  id uuid primary key default uuid_generate_v4(),
  listing_id uuid references marketplace_listings(id),
  version text not null,                       -- semver
  engine_min text,                             -- 兼容的最小引擎版本
  engine_max text,
  sha256 text not null,                        -- 包体 hash
  size_bytes bigint not null,
  storage_url text not null,                   -- S3/本地对象存储
  manifest jsonb not null,                     -- 见 10.C
  signature text not null,                     -- base64(ed25519)
  created_at timestamptz default now(),
  unique (listing_id, version)
);

-- 订单与授权（Entitlement）
create table marketplace_orders (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  listing_id uuid references marketplace_listings(id),
  version text,                                -- 购买时的版本（可空：表示始终可更新）
  quantity int not null default 1,             -- 席位数
  amount_cents bigint not null,
  currency text not null default 'usd',
  provider text not null,                      -- stripe
  external_order_id text,                      -- stripe checkout/ payment intent id
  status text not null default 'pending',      -- pending|paid|refunded|canceled
  created_at timestamptz default now()
);

alter table marketplace_entitlements
  add column listing_id uuid references marketplace_listings(id),
  add column version text,                     -- 授权的版本上限（如 "~1.2"）
  add column seats int not null default 1,
  add column device_bound boolean not null default true,
  add column created_via_order uuid references marketplace_orders(id);

create table marketplace_installs (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  listing_id uuid references marketplace_listings(id),
  version text not null,
  status text not null default 'installed',    -- installed|revoked|pending_update
  created_at timestamptz default now(),
  unique (device_id, listing_id)
);

-- 评分与审计
create table marketplace_reviews (
  id uuid primary key default uuid_generate_v4(),
  listing_id uuid references marketplace_listings(id),
  user_id uuid references users(id),
  rating int check (rating between 1 and 5),
  comment text,
  created_at timestamptz default now()
);
```

---

# 10.C 工作流打包与签名（WFPack）

**包格式：`.wfpack.tgz`**（tar.gz），包含：

```
/manifest.json
/workflows/*.json          # 一个或多个 Workflow（LP/HP 等）
// 可选依赖：提示词包、schema、锚点模板等
/prompts/*.md
/schemas/*.json
/assets/**                 # 锚点图片、模板
```

**`manifest.json` 字段（关键）**：

```json
{
  "key": "wechat.autoreply.v1",
  "name": "微信自动回复（销售）",
  "version": "1.0.0",
  "publisher": {
    "id": "pub_...","name":"ACME",
    "pubkey_ed25519": "base64-raw-pubkey"
  },
  "engine": { "min": "0.4.0", "max": "0.6.x" },
  "workflows": [
    { "file": "workflows/hp.json", "entry": true },
    { "file": "workflows/lp.json" }
  ],
  "requires": {
    "adapters": ["wechat"],             // 适配器要求
    "actions": ["chat.*","ocr.*","mq.*","api.*"],
    "permissions": {
      "ui_automation": true,
      "network": ["api_base"],          // 只能访问配置的 API_BASE
      "file_access": false
    }
  },
  "vars_schema": {                      // 安装时要填写的变量（如 ROI、输入框坐标）
    "app": {"type":"string","enum":["wechat","slack"],"default":"wechat"},
    "input_box": {"type":"object","required":["x","y"]}
  },
  "post_install": {
    "create_topics": ["device.${device_id}.${app}.hp.fifo"]
  }
}
```

**签名**：

* 计算包体 `sha256`；使用发布者的 **ed25519** 私钥生成签名，写入 `marketplace_versions.signature`
* **客户端**有引擎内置的“根信任（Root）”：允许的发布者公钥（或从服务器拉取 publisher 公钥白名单）
* 安装时：校验 `sha256`、校验 `ed25519` 签名与**发布者公钥**匹配，**且发布者在服务器标记 active**

> 参考伪代码（客户端校验）：

```python
# verify_wfpack.py
import hashlib, json, base64, nacl.signing
def verify(pkg_bytes, manifest, signature_b64, publisher_pubkey_b64):
    digest = hashlib.sha256(pkg_bytes).digest()
    sig = base64.b64decode(signature_b64)
    vk = nacl.signing.VerifyKey(base64.b64decode(publisher_pubkey_b64))
    vk.verify(digest, sig)  # raise if invalid
    # 同时检查 manifest.publisher.pubkey 与服务器返回的 publisher 公钥一致
    return True
```

---

# 10.D 发布者（Publisher）入驻与上架流程

1. **发布者入驻**（Publisher Portal / API）

   * `POST /marketplace/publishers`（管理员或邀请制），上传**公钥**与**结算账户**（Stripe Connect）
   * **KYC/KYB** 可后续补

2. **版本上传**

   * `POST /marketplace/listings` 创建 Listing（key/title/price 等）
   * `POST /marketplace/listings/:id/versions` 上传 `.wfpack.tgz`

     * 服务器计算 `sha256`，保存到对象存储（S3/MinIO/本地）
     * 校验引擎版本区间与签名 → 入库版本记录
     * 更新 `listings.latest_version`

3. **可见性与价格**

   * `visibility=public/unlisted/private`
   * 价格对应 Stripe Price（或内部价格）映射表

---

# 10.E 购买→授权→安装

## 10.E.1 用户购买（服务端）

* `POST /marketplace/checkout`：传 `listing_id`、`quantity`（席位）→ 返回 Stripe Checkout URL
* Webhook（Stripe）：`checkout.session.completed` → 写 `marketplace_orders`（paid）并创建/更新 `marketplace_entitlements`

  * `seats=quantity`，`device_bound=true`（默认）
  * `version` 可设为 `^1`（允许小版本更新）

## 10.E.2 客户端安装（API Only）

* `GET /marketplace/entitlements`（需 JWT）：返回用户可用的授权列表（含 `listing_id/version/seats`）
* `POST /marketplace/install`：参数 `listing_id`、`device_id`

  * 服务器校验：该用户有 entitlement、seat 未超限；返回**一次性下载 URL + 安装令牌**（短时效）
* 客户端下载包 → `verify_wfpack` → 解包到 `~/.autoagent/workflows/<key>/<version>/`
* 按 `manifest.vars_schema` 提示本地填写 ROI 等变量（存入 `~/.autoagent/workflows/<key>/config.json`）
* 引擎把 `workflows/*.json` **注册**到本地可用清单（带 **Publisher/Key/签名指纹**）

> 安装回执：
>
> * `POST /marketplace/installed`：上报 `device_id/listing_id/version/sha256` → 服务器入 `marketplace_installs`

## 10.E.3 运行授权校验（客户端）

* 每次启动 workflow 前：

  * 先查**本地缓存**（安装回执 + token 还在有效期）
  * 同步向 `/marketplace/entitlements/validate` 发送校验（返回“席位剩余/是否撤销/版本是否过期”）
  * **离线宽限**：校验失败但离线 → 给 24h 宽限（可配置），并打标记

---

# 10.F 更新与回滚

* 服务器端：`GET /marketplace/listings/:id/versions` 返回可用版本
* 客户端策略：

  * **Auto（默认）**：同主线（`^1.y.z`）自动升级到 `latest_version`
  * **Pinned**：固定在某一小版本（例如 1.3.x）
  * **Rollback**：一键回滚到前一版本（保留旧目录）

> 更新通告：
>
> * 服务器向 **控制队列** `device.<id>.control.fifo` 推送 `{"cmd":"MARKETPLACE_UPDATE","listing_id":...,"version":"1.2.1"}`

* 客户端接到后：若不在运行该工作流，则自动更新；若在运行 → 置为 `pending_update`

---

# 10.G 收益分账与退款

* `marketplace_orders.amount_cents` 按售价计收；周期性任务计算**分成**（例如平台 20%）
* 写 `payouts`（略）并通过 Stripe Connect 转账
* 退款：Stripe Webhook `charge.refunded` → 标记订单 `refunded`，并将 `marketplace_entitlements` 置失效；客户端下次校验后**撤销安装**（`status=revoked`）

---

# 10.H API 一览（服务器）

**用户侧**

* `GET /marketplace/listings?cat=&q=`：搜索/浏览
* `GET /marketplace/listings/:id`：详情 + 最新版本信息
* `POST /marketplace/checkout`：购买（返回支付 URL）
* `GET /marketplace/entitlements`：我的授权
* `POST /marketplace/install`：申请安装（校验 seat，返回下载 URL + token）
* `POST /marketplace/installed`：安装回执
* `POST /marketplace/entitlements/validate`：运行时校验（带 device\_id/listing\_id）

**发布者侧（Portal）**

* `POST /marketplace/publishers`：创建发布者
* `POST /marketplace/listings`：创建 Listing
* `POST /marketplace/listings/:id/versions`：上传 `.wfpack.tgz`（表单）
* `POST /marketplace/listings/:id/visibility`：上/下架
* `GET /marketplace/revenue`：收益报表（聚合 `marketplace_orders`）

**管理员**

* `POST /marketplace/listings/:id/revoke`：紧急下架并标记“强制撤销”
* `POST /marketplace/entitlements/:id/revoke`：撤销单用户授权（欺诈/退款）

> 全部 API 走 JWT 鉴权；**客户端永不直连 PG**。

---

# 10.I 客户端改造

* **Marketplace 面板（最小 UI）**：

  * 列出已购工作流（来自 `/entitlements`）
  * 按一下“安装”→ 调用 `/install` → 下载、校验签名、解包、收集变量、写本地配置
  * 展示“更新可用”/“已撤销”状态
* **引擎校验钩子**：`core/loader.py` 在载入 workflow 前执行：

  1. 读取 `manifest` 与签名指纹
  2. 校验 Publisher 白名单
  3. 校验 **权限白名单**（`actions` 与 `permissions`）——若用到未声明的动作/权限，拒绝载入
* **控制队列**：接收 `MARKETPLACE_UPDATE` 指令（阶段 6 的 control loop 即可复用）

---

# 10.J 权限与安全（务必落地）

* **动作白名单**：每个包的 `manifest.requires.actions` 限定允许调用的动作前缀（如 `chat.*`、`ocr.*`）。引擎执行前检查动作是否在白名单内。
* **系统权限**：

  * `ui_automation=true`：允许键鼠/窗口操作
  * `network=["api_base"]`：允许访问的域；客户端 SDK 在网络层强校验，防止包内随意外呼
  * 默认 `file_access=false`：禁止文件写入除工作目录外的位置
* **签名信任策略**：

  * 根信任：`trusted_publishers.json`（服务器同步/签发）
  * 客户端拒绝加载**未受信**或**被撤销**发布者的包
* **供应链**：`sha256` + `ed25519`；所有下载都带 **短时效 token**；禁止明文 HTTP

---

# 10.K 开发联调步骤（本地）

1. **创建发布者**（管理员）

   * 生成 ed25519 密钥对（开发机）
   * `POST /marketplace/publishers` 上报公钥与结算账户（伪）

2. **打包**

   * 将一套已验证的 `stage7_hp_generic.json + stage7_lp_generic.json` 放入 `/workflows/`
   * 写 `manifest.json`（如上）
   * `tar -czf wechat.autoreply.v1-1.0.0.wfpack.tgz ./manifest.json ./workflows ./assets`
   * 计算 sha256；用私钥签名 → `signature`

3. **上架**

   * `POST /marketplace/listings` 创建 Listing
   * `POST /marketplace/listings/:id/versions` 上传包（表单包含 `signature`、`sha256`）
   * 将 Listing 设为 `public`

4. **购买**

   * 用普通用户调用 `POST /marketplace/checkout` → 浏览器支付（Stripe 测试卡）
   * Webhook 写入 `orders` 与 `entitlements`

5. **安装（客户端）**

   * `/marketplace/entitlements` 拉取 → `/install` 获取下载 URL
   * 客户端下载→`verify_wfpack`→解包→注册
   * 运行：在 Marketplace 面板点击“启动”，HP/LP 进入可见运行状态

6. **更新**

   * 发布 1.0.1 → 服务器向设备 CONTROL 队列发 `MARKETPLACE_UPDATE` → 客户端自动更新/标记待更新

---

# 10.L 成功标准

* 能把一个**真实可用**的工作流（如“微信自动回复”）**上架**并**售卖**
* 购买后在客户端**一键安装**，运行时**授权校验通过**，**签名有效**
* 超过 seat 数或授权撤销时，客户端下一次校验**禁止运行**
* 上线新版本后，设备能**自动更新**或**提示更新**；异常可**回滚**
* **全链路不直连 PG**，一切通过 API + S3/对象存储 + SQS

---

# 10.M 下一步（可选增强）

* **差分更新**（bsdiff/rsync 校验），降低包体
* **配置向导**（引导填写 ROI、快捷键、锚点自动采集）
* **安全审计**：上架前自动做静态检查（动作黑名单、网络域校验）
* **试用/退款**：时间/次数限制的试用版（自动发 trial entitlement）
* **团队授权**：企业账号把席位分配给下属设备
* **内置评分/反馈**：`marketplace_reviews` 前端


**阶段 11｜稳健性 & 反检测 & 容错**。这一阶段让你的桌面自动化在真实环境里“更像人、更耐打、可自我修复”，并且保持：**OCR 在客户端本地**、**只走 API/SQS**、**与阶段 6 的暂停/恢复、阶段 7–10 的设备/计费/市场**完美兼容。

---

# 11.A 目标（完成后具备）

* 动作**人类化**（键鼠节流、路径曲线、微随机、失误与纠正）。
* 视觉**鲁棒**（多锚点、多尺度、多主题、DPI 自适应、滚动终止可靠）。
* OCR 本地增强（语言/方向/版面模式、缓存与后处理）。
* 引擎**防崩与自愈**（动作超时、看门狗、熔断、幂等重试、断网/失焦恢复）。
* **反检测**策略（前台/窗口焦点、速率限制、输入噪声、特征抖动）。
* **可观测性**（结构化事件、指标、局部录屏/取证快照）、**Chaos** 注入与验收套件。

---

# 11.B 威胁面与约束（WeChat/Slack/飞书等通用）

* UI 自动化“可疑信号”：**恒定移动速度、直线轨迹、零打字错误、毫秒级固定节奏、后台窗口输入**。
* 视觉脆弱点：主题/缩放变化、DPI、字体包、夜间模式、国际化、窗口遮挡、弱网络导致延迟渲染。
* 业务脆弱点：重复发消息、漏 ack、滚动不到底、评论展开漏点、对端反爬节流。

---

# 11.C 人类化输入工具包（Client 侧库）

目录：`client/humanize/`

```
human_mouse.py   # 轨迹与点击
human_keyboard.py# 打字与纠错
rate_limiter.py  # 令牌桶 + 抖动
focus_guard.py   # 前台/窗口焦点守护
```

## 11.C.1 鼠标（曲线、微抖动、误差+修正）

```python
# client/humanize/human_mouse.py
import math, random, time
from client.adapters.oswin import OS  # 你已有 OS 适配器

def _bezier(p0, p1, p2, p3, t):
    u=1-t; return (
        u*u*u*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t*t*t*p3[0],
        u*u*u*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t*t*t*p3[1]
    )

def move_to(x, y, duration=0.6, jitter=1.5):
    sx, sy = OS.get_cursor()
    dx, dy = x + random.uniform(-jitter,jitter), y + random.uniform(-jitter,jitter)
    # 控制点：弧形，避直线
    ctrl1 = (sx + (dx-sx)*0.3 + random.uniform(-20,20), sy + (dy-sy)*0.1 + random.uniform(-20,20))
    ctrl2 = (sx + (dx-sx)*0.6 + random.uniform(-20,20), sy + (dy-sy)*0.9 + random.uniform(-20,20))
    st = time.time()
    while True:
        t = min(1.0, (time.time()-st)/duration)
        nx, ny = _bezier((sx,sy), ctrl1, ctrl2, (dx,dy), t)
        OS.move(int(nx), int(ny))
        time.sleep(0.008 + random.uniform(0,0.006))
        if t>=1: break
    # 修正到精确点（模拟“摆正”）
    OS.move(x, y); time.sleep(random.uniform(0.02,0.07))

def human_click(button="left"):
    # 触发前轻微停顿，模拟“确认”
    time.sleep(random.uniform(0.06,0.18))
    OS.mouse_down(button); time.sleep(random.uniform(0.03,0.11)); OS.mouse_up(button)

def human_move_and_click(x, y):
    dur = random.uniform(0.45, 0.9)
    move_to(x, y, duration=dur)
    human_click()
```

## 11.C.2 键盘（节流、偶发错字+退格）

```python
# client/humanize/human_keyboard.py
import random, time
from client.adapters.oswin import OS

def type_text(s: str):
    for ch in s:
        OS.key_tap(ch)
        base = 0.03 if ch==' ' else 0.06
        time.sleep(base + random.uniform(0, 0.08))
        # 低概率打错并纠正（不在 URL/代码块）
        if ch.isalpha() and random.random()<0.02:
            wrong = random.choice("asdfghjkl")
            OS.key_tap(wrong)
            time.sleep(0.12+random.uniform(0,0.1))
            OS.key_tap("backspace")
            time.sleep(0.05+random.uniform(0,0.05))
```

## 11.C.3 全局速率限制（避免过“机械”）

```python
# client/humanize/rate_limiter.py
import time, random
class TokenBucket:
    def __init__(self, rate_per_sec, burst):
        self.rate = rate_per_sec; self.capacity = burst; self.tokens = burst; self.t = time.time()
    def take(self, n=1):
        now = time.time(); self.tokens = min(self.capacity, self.tokens + (now-self.t)*self.rate); self.t = now
        if self.tokens >= n: self.tokens -= n; return True
        return False

ui_bucket = TokenBucket(rate_per_sec=5, burst=8)  # 每秒 5 次动作，突发 8
def ui_guard():
    while not ui_bucket.take():
        time.sleep(0.05 + random.uniform(0,0.05))
```

> 在每个 `chat.*`、`click_coordinates` 动作前调用 `ui_guard()`；结合阶段 6 的 safepoint，效果更自然。

## 11.C.4 焦点守护（防后台发消息）

```python
# client/humanize/focus_guard.py
import time
from client.adapters.oswin import OS, Window

def require_foreground(app_name: str, timeout=5.0):
    st = time.time()
    while time.time()-st < timeout:
        if Window.active_process_name().lower().startswith(app_name):
            return True
        time.sleep(0.15)
    return False
```

> 在 `chat.send_text`、`chat.focus_contact` 前校验；失败则**暂停并提示**或重试 BringToFront。

---

# 11.D 视觉鲁棒升级（多锚点/多尺度/多主题）

目录：`client/vision2/`

```
anchors.py        # 多锚管理 + 主题集
templatematch.py  # 多尺度匹配 + NCC/SSIM
scroll_stop.py    # 滚动终止判定（差分+哨兵）
```

## 11.D.1 多锚管理

```python
# client/vision2/anchors.py
from dataclasses import dataclass
from typing import List, Tuple
@dataclass
class Anchor:
    name: str
    templates: List[str]   # 多主题/多分辨率路径
    roi: Tuple[int,int,int,int] | None = None
    threshold: float = 0.82
```

## 11.D.2 多尺度匹配 + 置信融合

```python
# client/vision2/templatematch.py
import cv2, numpy as np
def match_multi(img, tmpl, scales=(0.75,0.9,1.0,1.1,1.25)):
    best = None
    for s in scales:
        t = cv2.resize(tmpl, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(r)
        if not best or maxVal > best[0]:
            best = (maxVal, maxLoc, t.shape[::-1])
    return best  # (score, (x,y), (w,h))

def ssim(a,b):  # 备用一致性检查（简化）
    from skimage.metrics import structural_similarity
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY); b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    return structural_similarity(a,b)
```

## 11.D.3 滚动终止（差分 + 哨兵锚）

```python
# client/vision2/scroll_stop.py
import numpy as np, time
def should_stop(prev_img, curr_img, pixel_thresh=0.98):
    diff = np.mean((prev_img.astype(np.int16)-curr_img.astype(np.int16))==0)
    return diff > pixel_thresh  # 画面几乎不变 → 到底或卡住

def scroll_until_sentinel(dom, vision, sentinel_anchor, max_swipes=30):
    prev = vision.capture()
    for i in range(max_swipes):
        dom.scroll_page()
        time.sleep(0.4)
        cur = vision.capture()
        if vision.find(sentinel_anchor):
            return True
        if should_stop(prev, cur):
            return True
        prev = cur
    return False
```

> 组合策略：**先找哨兵**（“没有更多了”、“到底了”），找不到再用**差分阈值**兜底。

---

# 11.E OCR 本地增强（仍在客户端）

* **Tesseract**：启用 `--oem 1 --psm 6/11`，中英双语包；**方向检测** `--psm 0` 预检；表情/昵称特殊符号白名单。
* **版面分块**：用连通域/行分割，避免整屏 OCR；**消息气泡 ROI** 提速提准。
* **缓存**：图片 SHA1 → 文本；同一气泡不重复 OCR。
* **后处理**：简单规则修正（全角半角、标点/emoji 归一化）；必要时本地小模型纠正（可选）。

示例动作参数：

```json
{ "do":"ocr.run", "roi":"@bubble_bbox", "lang":"chi_sim+eng", "psm": 6, "cache": true }
```

---

# 11.F 引擎自愈：超时/熔断/幂等

新增模块：`core/resilience.py`

```python
import time, random
class RetryPolicy:
    def __init__(self, attempts=3, base=0.3, max_wait=3.0):
        self.attempts=attempts; self.base=base; self.max_wait=max_wait
    def backoff(self, i): return min(self.max_wait, self.base*(2**i))*(1+random.uniform(-0.2,0.2))

class CircuitBreaker:
    def __init__(self, fail_threshold=5, cool_sec=30):
        self.fail=0; self.ts=0; self.th=fail_threshold; self.cool=cool_sec
    def allow(self):
        if self.fail>=self.th and time.time()-self.ts < self.cool: return False
        return True
    def record(self, ok):
        if ok: self.fail=0
        else: self.fail+=1; self.ts=time.time()
```

**动作包装**（以 `click_coordinates` 为例）：

```python
# actions/click_coordinates.py
from core.resilience import RetryPolicy, CircuitBreaker
RP = RetryPolicy(attempts=4, base=0.2, max_wait=2.0)
CB = CircuitBreaker(fail_threshold=6, cool_sec=45)

@register_action("click_coordinates")
def click_coordinates(step, ctx, bbox, **_):
    if not CB.allow(): return {"skipped":"circuit_open"}
    x,y,w,h = bbox_to_click_point(bbox)
    for i in range(RP.attempts):
        try:
            human.ui_guard()
            human.human_move_and_click(x,y)
            return {"ok":True}
        except Exception:
            time.sleep(RP.backoff(i))
    CB.record(False); return {"ok":False}
```

**队列幂等**：所有 HP 消息带 `idempotency_key`；云端已在阶段 8 实现去重，客户端重复 ack 安全。

**看门狗**：Scheduler 每 N 秒记录**心跳**；状态机超过 `state_timeout_s` 未推进 → 触发 `PAUSE` + 快照；（网络恢复后 `RESUME`）。

---

# 11.G 反检测守则（默认开启，可配置）

* **仅前台输入**：失败则 BringToFront；连续失败 → 停止并提示“需用户解锁窗口/取消全屏”。
* **动作间隔抖动**：加入 `[+0~80ms]` 微随机，整体行动速率由 `TokenBucket` 控制。
* **路径曲线 & 停顿**：曲线移动 + 落点微修正，点击前短暂停。
* **不发“隐形按键”**：禁止后台窗口键入；禁止系统级粘贴洪流。
* **错字纠正**：低概率错字 + Backspace（避免“机械完美”）。
* **节能**：窗口被遮挡/最小化 → 暂停 LP/HP，防误操作。

> 以上策略集中在 **客户端** 实现，不触碰服务端或数据库权限。

---

# 11.H 观测 & 取证

* 事件：`ui.action`, `vision.match`, `ocr.run`, `llm.submit`, `mq.requeue`, `pause/resume`。
* 指标：动作成功率、平均匹配置信、滚动次数、OCR 命中率、平均响应时延。
* 取证：失败时**可选截屏**（脱敏：遮盖联系人名/手机号），保存在 `artifacts/<run_id>/fails/`。
* 隐私：上传 API 仅发**事件摘要**与**数值指标**，**不上传截图**（默认）；如需远程诊断，用户勾选后临时启用。

---

# 11.I 配置与灰度

* 远程**Feature Flag**（API）：

  * `humanize.enabled`、`humanize.level`（low/med/high）
  * `vision.scales`、`match.threshold`
  * `ocr.langs`、`ocr.psm`
* 本地 `~/.autoagent/config.yaml` 可覆盖；优先级：**远程** > 本地文件 > 包内默认。

---

# 11.J Chaos & 验收

**Chaos 注入脚本** `scripts/chaos_stage11.py`：

* 随机切后台、遮挡窗口、制造 200ms–2s 延迟、截屏返回全黑。
* 期望：工作流暂停/重试/熔断，不出现**连点错误**或**后台发消息**。

**验收标准**

* 在 WeChat/飞书/Slack 三种桌面端（不同主题/缩放）下：

  1. **100 次发送**成功率 ≥ 98%，无后台发送；
  2. **滚动终止**在“到底”与“评论已读完”两场景下成功检测率 ≥ 99%；
  3. OCR 同屏重复气泡**缓存命中** ≥ 80%，总体 OCR 耗时下降 ≥ 30%；
  4. 短时断网/窗口切走 → **不误操作**，恢复后可继续；
  5. Chaos 注入下**无业务级事故**（不会连发/错发）。

---

# 11.K 集成步骤（怎么落到你现有仓库）

1. `client/humanize/*` 与 `client/vision2/*` 落地；在 `actions/chat.*`、`actions/click_coordinates` 内引入。
2. 在 `examples/` 的工作流 JSON 中，给关键动作加 `state_timeout_s`（如 8–15s）。
3. 在 `client/scheduler.py` 中加入**看门狗**与**前台校验**钩子；在 Safepoint 后调用 `focus_guard.require_foreground`。
4. OCR 动作扩展参数（lang/psm/cache/roi）。
5. `server` 无需改动；只需扩展 `/api/events` 接收**观测事件**（如已有则复用）。
6. 跑 `scripts/chaos_stage11.py` + 实机点击 100 次回归。

---

# 11.L 风险与兜底

* 曲线轨迹与打字错字率**不宜过高**（业务可疑）；默认 `humanize.level=med`。
* 屏幕 DPI/多显示器：锚点模板按 100%/125%/150% 三档各一套；渲染时按 DPI 选择。
* 低端机：人类化动作会增加延迟；提供 `low` 模式（减少抖动/误差模拟）。
* 国际化：优先文字锚 + 图标锚混合；仅图标锚在主题变换时更稳定。

---

做到这里，**阶段 11** 就把稳定性、自然度和反检测整体拉起来了，而且完全兼容你之前各阶段的结构（SQS、暂停/恢复、计量、市场安装）。


阶段12:
好，进入**阶段 12｜跨端（移动/远程桌面）与云端回放/诊断**。这一阶段完成后，你可以：

* 在**桌面端**与\*\*移动端（Android 首发）\*\*跑相同工作流（通过“适配器层”抽象动作）。
* 为每次运行生成**可回放的“云端录像”与事件时间线**，支持**近实时远程协助**与**问题定位**。
* 全程遵守你的底线：**OCR 继续在客户端**；客户端**绝不直连 PG**；所有工件通过 **API + S3（或 MinIO）+ SQS**。

我把这一阶段拆成能直接落地的 8 个部分：架构、表结构、API、客户端改造（桌面录制+隐私脱敏+近实时上传）、Android 适配器、远程协助（直播/控制）、Web 回放 UI（极简）、本地联调与验收。

---

# 12.A 架构总览

```
┌──────────────────────────┐
│  Web Console (React)     │── 查看回放 / 实时协助（WebSocket）
└──────────┬───────────────┘
           │
     ┌─────▼─────┐     ┌────────────────┐      ┌─────────┐
     │ API/Server│◀────│ Postgres       │      │  Redis   │
     │ (Node)    │     │ (元数据/审计)  │      │(低延迟) │
     └───┬───┬───┘     └────────────────┘      └─────────┘
         │   │
         │   └──S3/MinIO（包体、录屏分片、快照、事件导出）
         │
 ┌───────▼────────┐     ┌─────────────────────┐
 │ SQS (LocalStack│     │ Mobile Agent (Android)│
 │ / AWS)         │     │ 适配器：adb/uia2     │
 └───────▲────────┘     └──────────┬──────────┘
         │                          │
  ┌──────┴─────────┐                │
  │ Desktop Client │  录屏→脱敏→分片上传│
  │ (Windows/macOS)│──事件→API/SQS   │
  └────────────────┘                │
```

---

# 12.B 数据库（仅服务端访问）

> 新增为 `40-diagnostics.sql`；保持与前面阶段表解耦。

```sql
-- 一次工作流运行的“会话”
create table run_sessions (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  workflow_key text not null,
  version text,
  run_id text not null,                    -- 客户端生成的短ID（用于文件名）
  started_at timestamptz default now(),
  ended_at timestamptz,
  status text not null default 'running',  -- running|succeeded|failed|aborted
  meta jsonb default '{}'::jsonb
);

-- 结构化事件（轻量，可多到百万条）
create table run_events (
  id bigserial primary key,
  session_id uuid references run_sessions(id) on delete cascade,
  ts timestamptz not null,                 -- 事件发生时间（客户端上报）
  level text default 'info',
  category text,                           -- ui|vision|ocr|llm|mq|state|error
  name text,                               -- e.g. click|find_anchor|ocr.run
  data jsonb default '{}'::jsonb
);
create index on run_events(session_id, ts);

-- 录屏与快照素材索引（文件在 S3）
create table run_artifacts (
  id uuid primary key default uuid_generate_v4(),
  session_id uuid references run_sessions(id) on delete cascade,
  kind text not null,                      -- 'recording'|'snapshot'|'trace'
  s3_key text not null,
  size_bytes bigint,
  sha256 text,
  content_type text,
  created_at timestamptz default now(),
  meta jsonb default '{}'::jsonb           -- e.g. fps, width, height, segment: [start,end]
);

-- 实时协助会话（WebSocket/中继）
create table assist_sessions (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  run_session_id uuid references run_sessions(id),
  started_at timestamptz default now(),
  ended_at timestamptz,
  status text default 'open'               -- open|closed
);
```

---

# 12.C 服务端 API（Node/Express）

## 12.C.1 运行会话与事件

```js
// server/src/diag.js
import express from "express";
import { pool } from "./db.js";
import { authRequired } from "./middleware.js";
import { presign, putObject } from "./s3.js";
export const diag = express.Router();

// 开始/结束会话
diag.post("/runs/start", authRequired, async (req,res)=>{
  const { device_id, workflow_key, version, run_id, meta } = req.body || {};
  const { rows } = await pool.query(
    `insert into run_sessions(user_id,device_id,workflow_key,version,run_id,meta)
     values($1,$2,$3,$4,$5,$6) returning id`,
    [req.user.user_id, device_id, workflow_key, version||null, run_id, meta||{}]
  );
  res.json({ session_id: rows[0].id });
});

diag.post("/runs/end", authRequired, async (req,res)=>{
  const { session_id, status, meta } = req.body || {};
  await pool.query(
    `update run_sessions set ended_at=now(), status=$2, meta=coalesce(meta,'{}'::jsonb) || $3 where id=$1`,
    [session_id, status||'succeeded', meta||{}]
  );
  res.json({ ok:true });
});

// 批量事件（数组）
diag.post("/runs/events", authRequired, async (req,res)=>{
  const { session_id, events } = req.body || {};
  const values = [];
  for (const e of (events||[])) {
    values.push(`('${session_id}', '${e.ts}', '${e.level||'info'}', '${e.category||''}', '${e.name||''}', '${JSON.stringify(e.data||{})}')`);
  }
  if (values.length) {
    await pool.query(`insert into run_events(session_id, ts, level, category, name, data) values ${values.join(",")}`);
  }
  res.json({ n: values.length });
});

// 素材登记（客户端先上传 S3，再登记）
diag.post("/runs/artifacts", authRequired, async (req,res)=>{
  const { session_id, kind, s3_key, size_bytes, sha256, content_type, meta } = req.body || {};
  const r = await pool.query(
    `insert into run_artifacts(session_id,kind,s3_key,size_bytes,sha256,content_type,meta)
     values($1,$2,$3,$4,$5,$6,$7) returning id`,
    [session_id, kind, s3_key, size_bytes||null, sha256||null, content_type||null, meta||{}]
  );
  res.json({ artifact_id: r.rows[0].id });
});

// 供客户端请求某 key 的上传签名（可选：也可由客户端直传再登记）
diag.post("/runs/artifacts/presign", authRequired, async (req,res)=>{
  const { key, content_type } = req.body || {};
  // 这里只返回下载 presign；真正上传你可用 S3 的 POST policy 或直接 PutObject（服务端代理）
  res.json({ upload: null, download: await presign(key) });
});
```

在 `server/src/index.js` 里挂载：

```js
import { diag } from "./diag.js";
app.use("/diag", diag);
```

---

# 12.D 客户端改造（桌面端）：录屏/脱敏/分片上传

## 12.D.1 录屏器（轻量：PNG 快照序列或 MJPEG）

两条路径：

1. **快照序列（默认）**：每 500ms 抓屏一次（PNG），体积适中、易脱敏；回放时逐帧渲染。
2. **MJPEG**：内存合成 MJPEG 流（更小），复杂度略高。

先用路径 1，跨平台更稳。

```python
# client/recorder.py
import io, time, threading, hashlib, requests, zlib
from PIL import Image, ImageFilter, ImageDraw
from pathlib import Path

class Recorder:
    def __init__(self, api_base, token, device_id, session_id, privacy):
        self.api_base=api_base; self.token=token
        self.device_id=device_id; self.session_id=session_id
        self.privacy=privacy or {"blur_regions":[], "pixelate_text":True}
        self.stop=False; self.t=None

    def _capture(self):
        # 用你的 OS 截屏适配器
        from client.adapters.oswin import OS
        img = OS.screenshot()  # PIL Image
        # 脱敏：遮挡敏感区域（用户名、头像、二维码等）
        draw = ImageDraw.Draw(img)
        for (x,y,w,h) in self.privacy.get("blur_regions", []):
            region = img.crop((x,y,x+w,y+h)).filter(ImageFilter.GaussianBlur(radius=12))
            img.paste(region, (x,y))
        return img

    def _upload_png(self, png_bytes, ts_ms):
        sha = hashlib.sha256(png_bytes).hexdigest()
        key = f"runs/{self.session_id}/{ts_ms}.png"
        # 直接 PUT 到对象存储：你也可以先向 /diag/runs/artifacts/presign 索要上传策略
        # 这里简化：服务端开放 /upload 代理 PutObject（生产建议直传 S3）
        r = requests.post(f"{self.api_base}/upload",
                          headers={"Authorization": f"Bearer {self.token}"},
                          files={"file": ("frame.png", png_bytes, "image/png")},
                          data={"key": key}, timeout=10)
        r.raise_for_status()
        # 登记索引
        requests.post(f"{self.api_base}/diag/runs/artifacts",
                      headers={"Authorization": f"Bearer {self.token}", "Content-Type":"application/json"},
                      json={"session_id": self.session_id, "kind":"snapshot", "s3_key": key,
                            "size_bytes": len(png_bytes), "sha256": sha, "content_type":"image/png",
                            "meta":{"ts_ms": ts_ms}}, timeout=8).raise_for_status()

    def start(self, fps=2):
        interval = 1.0/float(fps)
        def loop():
            while not self.stop:
                t0 = time.time()
                ts_ms = int(t0*1000)
                img = self._capture()
                buf = io.BytesIO(); img.save(buf, format="PNG", optimize=True); data = buf.getvalue()
                self._upload_png(data, ts_ms)
                dt = time.time()-t0
                time.sleep(max(0, interval - dt))
        self.t = threading.Thread(target=loop, daemon=True); self.t.start()

    def stop_and_wait(self):
        self.stop=True
        if self.t: self.t.join(timeout=3)
```

> **隐私默认开启**：仅在本地做马赛克/遮挡，默认不上传整屏长视频。若用户授权“远程诊断”，再放宽 FPS/区域。

## 12.D.2 事件时间线（批量上报）

```python
# client/telemetry.py
import time, requests
class Telemetry:
    def __init__(self, api_base, token, session_id):
        self.api_base=api_base; self.token=token; self.session_id=session_id; self.buf=[]
    def log(self, category, name, data=None, level="info"):
        self.buf.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                         "level": level, "category": category, "name": name, "data": data or {}})
        if len(self.buf)>=50: self.flush()
    def flush(self):
        if not self.buf: return
        b=self.buf; self.buf=[]
        requests.post(f"{self.api_base}/diag/runs/events",
                      headers={"Authorization": f"Bearer {self.token}", "Content-Type":"application/json"},
                      json={"session_id": self.session_id, "events": b}, timeout=8)
```

在 Runner 中：状态进入/退出、关键动作成功/失败、OCR 调用、LLM 往返等均 `telemetry.log(...)`。

---

# 12.E Android 适配器（首发）

目标：在 Android **原生微信/小红书**上跑与桌面版语义相同的工作流。
实现方式：**adb + uiautomator2**（稳定、无需 root），屏幕获取用 `adb exec-out screencap -p`（或 `minicap` 更快），输入用 `adb shell input` 与 uia2 的控件操作。

## 12.E.1 依赖与启动

* 安装 `adb`、`python-uiautomator2`：`pip install uiautomator2`
* 手机开启 **USB 调试**；或 Wi-Fi ADB。
* 连接：`adb devices`。

## 12.E.2 适配器接口

```python
# client/adapters/android.py
import uiautomator2 as u2, subprocess, io
from PIL import Image

class AndroidAdapter:
    def __init__(self, serial=None):
        self.d = u2.connect(serial)  # 为空默认1台
    def tap(self, x, y):
        self.d.click(x, y)
    def swipe(self, x1,y1,x2,y2,dur_ms=300):
        self.d.swipe(x1,y1,x2,y2,duration=dur_ms)
    def input_text(self, s):
        self.d.set_fastinput_ime(True)  # 提速
        self.d.send_keys(s, clear=False)
    def screenshot(self):
        # 用 u2 自带截图或 adb screencap（后者快且一致）
        png = self.d.screenshot(format='raw')  # 或 self.d.screenshot()
        return png  # bytes

    # 高层封装：微信/小红书特定锚点
    def wechat_open_latest_unread(self):
        # 示例：找“未读”红点节点；这里建议结合 u2 selector + 屏幕 OCR 双保险
        self.d(resourceId="com.tencent.mm:id/badge").click_exists(timeout=0.5)

    def wechat_send_text(self, text):
        # 定位输入框并输入
        self.d(resourceId="com.tencent.mm:id/ay5").click()
        self.input_text(text)
        self.d(description="发送").click_exists(timeout=0.5)
```

## 12.E.3 动作映射（与桌面通用化）

把现有 `chat.*` 抽象为 `IChatAdapter`，由 `wechat.desktop` 与 `wechat.android` 两个实现；workflow 里仅写 `vars.app` 为 `wechat_desktop` 或 `wechat_android`。

```python
# client/actions/chat.py
class IChatAdapter:
    def focus_contact(self, name): ...
    def send_text(self, text): ...
    def find_unread(self): ...
    def capture_visible(self): ...

# 具体实现选择
def resolve_chat_adapter(ctx):
    app = ctx.vars.get("app", "wechat_desktop")
    if app == "wechat_android": return AndroidWechatAdapter(...)
    else: return DesktopWechatAdapter(...)
```

**OCR**仍在本地（手机截图传到客户端内存做 OCR，不落盘）。

---

# 12.F 远程协助（近实时预览 + 控制）

**目标**：支持在 Web 控制台**近实时看到设备屏幕**（2–3 FPS 即可诊断），并下发少量控制命令（暂停、继续、重新锚点、试探点击）。不做持续全控制，避免风险。

## 12.F.1 服务器中继（WebSocket）

```js
// server/src/assist_ws.js
import { WebSocketServer } from "ws";
import { pool } from "./db.js";

export function createAssistWSS(server){
  const wss = new WebSocketServer({ noServer: true });
  const rooms = new Map(); // roomId -> { viewers:Set<ws>, agent: ws|null }

  server.on("upgrade", (req, socket, head) => {
    if (!req.url.startsWith("/assist/ws")) return;
    wss.handleUpgrade(req, socket, head, (ws)=> wss.emit("connection", ws, req));
  });

  wss.on("connection", (ws, req)=>{
    // query: role=agent|viewer&room=<session_or_device_id>&token=JWT
    const url = new URL(req.url, "http://localhost");
    const role = url.searchParams.get("role");
    const room = url.searchParams.get("room");
    let entry = rooms.get(room) || { viewers: new Set(), agent: null };
    rooms.set(room, entry);

    if (role === "agent"){ entry.agent = ws; }
    else { entry.viewers.add(ws); }

    ws.on("message", (buf)=>{
      // 统一消息格式 {type:"frame"|"event"|"cmd", payload:{...}}
      const msg = JSON.parse(buf.toString());
      if (role === "agent" && msg.type === "frame"){
        // 转发帧给所有 viewer（限制频率可在 agent 端做）
        for (const v of entry.viewers) try{ v.send(buf); }catch{}
      } else if (role === "viewer" && msg.type === "cmd"){
        // 只转发控制指令给 agent
        if (entry.agent) entry.agent.send(buf);
      }
    });

    ws.on("close", ()=>{
      if (role === "agent") entry.agent = null;
      else entry.viewers.delete(ws);
    });
  });

  return wss;
}
```

在 `src/index.js` 里把 HTTP server 传入 `createAssistWSS(server)`；客户端与网页用 `wss://.../assist/ws?role=agent|viewer&room=<device_or_session>` 链接。

## 12.F.2 客户端 Agent 侧推流

复用 12.D 的截图，但不落 S3，直接**降采样 + JPEG**经 WS 推 2–3 FPS：

```python
# client/assist_stream.py
import time, io, json, threading
from PIL import Image
import websocket  # websocket-client

class AssistStreamer:
    def __init__(self, ws_url, os_adapter):
        self.ws_url=ws_url; self.os=os_adapter; self.stop=False
    def start(self, fps=3, scale=0.5, quality=60):
        def loop():
            ws = websocket.create_connection(self.ws_url)
            while not self.stop:
                img = self.os.screenshot()
                w,h = img.size; img = img.resize((int(w*scale), int(h*scale)))
                buf = io.BytesIO(); img.save(buf, format="JPEG", quality=quality)
                ws.send(json.dumps({"type":"frame","payload":{"ts":time.time()}}))
                ws.send_binary(buf.getvalue())
                time.sleep(1.0/fps)
            ws.close()
        threading.Thread(target=loop, daemon=True).start()
    def stop_and_wait(self): self.stop=True
```

> 简化实现：发送一个 JSON，再跟一包二进制作为同一帧；前端按顺序读取（或将二者封装成一条 ArrayBuffer）。

**控制命令**（示例）：

* `{"type":"cmd","payload":{"op":"PAUSE"}}` → 客户端调用 `scheduler.pause()`
* `{"type":"cmd","payload":{"op":"CLICK","x":1200,"y":640}}` → 人工试点一次（带审计）
* `{"type":"cmd","payload":{"op":"SET_BLUR","rect":[x,y,w,h]}}` → 动态追加脱敏区域

---

# 12.G Web 回放 UI（极简）

功能：列表会话 → 时间线 → 逐帧浏览；也能打开“实时协助”。

前端要点：

* 拉 `/diag/runs/:session/events`（你可添加 GET 接口）
* 拉 `/diag/runs/:session/artifacts?kinds=snapshot`，按 `ts_ms` 排序
* 左侧时间线（筛 category），右侧帧画面（点击时间线跳帧）
* “实时协助”按钮 → 打开 WS viewer：播放 agent 推送的 JPEG 帧，支持下发简单命令

> 出于篇幅，我不贴整页 React，只给**帧渲染核心**（MJPEG-like）：

```jsx
// 假设后端 WS 先发 JSON 再发二进制
function LiveViewer({wsUrl}){
  const canvasRef = React.useRef();
  React.useEffect(()=>{
    const ws = new WebSocket(wsUrl);
    let expectBinary = false;
    ws.binaryType = "arraybuffer";
    ws.onmessage = (ev)=>{
      if (typeof ev.data === "string"){
        const m = JSON.parse(ev.data);
        if (m.type === "frame") expectBinary = true;
      } else if (ev.data instanceof ArrayBuffer && expectBinary){
        expectBinary = false;
        const blob = new Blob([ev.data], {type:"image/jpeg"});
        const img = new Image();
        img.onload = ()=>{
          const c = canvasRef.current;
          c.width = img.width; c.height = img.height;
          c.getContext("2d").drawImage(img,0,0);
        };
        img.src = URL.createObjectURL(blob);
      }
    };
    return ()=> ws.close();
  }, [wsUrl]);
  return <canvas ref={canvasRef} style={{maxWidth:"100%"}} />;
}
```

---

# 12.H 安全与隐私默认值（务必执行）

* **默认不开启**实时协助推流；开启必须用户点击 + 有时效令牌（JWT → WS URL）。
* **帧率/分辨率限制**：默认 2 FPS、50% 缩放、JPEG 60 品质，并且**先脱敏再推流**。
* **事件脱敏**：`run_events.data` 里屏蔽手机号/邮箱（正则替换为 `***`）。
* **操作审计**：所有 viewer 下发的 `cmd` 都写 `run_events`（level=warn, category="assist"）。
* **API 与对象存储权限**：上传走短时签名或后端代理；公开访问一律禁止。

---

# 12.I 本地联调步骤（一把跑通）

1. **数据库迁移**：执行 `40-diagnostics.sql`。
2. **Server**：添加并挂载 `/diag/*`、`/assist/ws`；S3/MinIO 保持和之前相同配置。
3. **Desktop Client**：

   * 在 Runner 启动工作流时：

     1. `POST /diag/runs/start` → 得到 `session_id`
     2. 启动 `Recorder.start(fps=2)` 与 `Telemetry`
   * 在状态机关键节点 `telemetry.log(...)`；结束时 `runs/end`
4. **Android Agent**：插上手机，`adb devices`；在 `services_build` 里加入 `android` 适配器开关。
5. **Web 回放**：简单页面（或在你的控制台里加一个面板）拉取 `run_events` 与 `run_artifacts`（先用 `/diag/runs/artifacts` 简化）。
6. **实时协助**：

   * 客户端开启 `AssistStreamer` 连接 `ws://localhost:8080/assist/ws?role=agent&room=<device_id>`
   * 浏览器开 viewer：`?role=viewer&room=<device_id>`，应能看到 2–3 FPS 的缩略屏幕；点击“暂停”按钮发 `PAUSE` 命令，客户端应停。

---

# 12.J 验收标准

* 桌面与 Android 各跑一次**完整会话**，能在 Web 控制台看到：

  * 时间线（至少 100+ 事件）、回放帧（按时间排序无丢帧）。
  * 近实时预览（≥2 FPS）能稳定渲染 ≥ 3 分钟，指令下发有效，有审计记录。
* **隐私**默认保护：未授权不开启推流；快照均带遮挡；事件字段已做脱敏。
* 同一工作流仅切换 `vars.app`（`wechat_desktop` ⇄ `wechat_android`）即可跨端运行（核心动作兼容）。
* 客户端仍**不直连 PG**；所有索引/事件/素材登记都走 API。

---

# 12.K 风险与兜底

* **带宽/存储**：快照多会占用 S3；按会话/设备设置最大保留数（如 2k 帧）与 TTL（默认 7 天）。
* **移动端稳定性**：adb 连接易断；加“保活线程”自动 `reconnect`；uia2 启动失败自动重装。
* **跨端锚点**：安卓主题复杂，优先用 uia2 结构化节点；图像锚点做兜底。
* **WebSocket 负载**：多人同时看同一设备时，服务器中继可能成为瓶颈；可迁移至 **WebRTC**（后续阶段）。

---

到这里，**阶段 12** 完成落地：桌面 + Android 同时跑，云端可回放/诊断 + 近实时协助闭环已打通。

好，进入**阶段 13｜自动回归 & 可编排端到端测试（含 Chaos）**。目标是：每次改动从**动作层 → 引擎 → 队列 → 服务端 → 计费/市场 → 客户端**整链路都有可重复、稳定、可视化的验证，且能在 CI/CD 中一键跑完并做放行门槛。

---

# 13.A 我们要达到什么

* **稳定的测试金字塔**：单测（快）→ 组件集成（中）→ 全链路 E2E（少但有代表性）。
* **可重复**：冻结时间/随机种子、假外部依赖（LLM/OCR/屏幕/安卓）。
* **可观测**：生成事件时间线、截图/视频快照、覆盖率、SSIM/像素对比报告。
* **可编排**：`docker-compose.test.yml` 一键起整套依赖；CI 中并行分桶。
* **Chaos**：注入焦点丢失、SQS 延迟/丢包、OCR 误差、网络毛刺，验证自愈。

---

# 13.B 测试金字塔与范围

1. **单元（Unit）**

   * Python：条件表达式求值、变量/数据动作（`set_variable/get_list_item/query_data`）、转场规则解析、资源锁。
   * Node：API 鉴权/RBAC、明文/加密 API Key 写入与管理员揭示审计、市场签名校验、计费聚合。
2. **组件集成（IT）**

   * Worker ↔ Mock LLM（BYOK 路由、usage 计量、幂等）。
   * Marketplace：上架→上传→安装下载 URL→客户端验证签名。
   * Billing：`llm_usage → usage_rollups → invoices`。
3. **E2E（端到端）**

   * “微信自动回复”**桌面模拟器**（Fake UI）+ LP/HP 工作流完整闭环。
   * “小红书采集”滚动/展开/锚点/分页闭环。
   * **Android 适配**对等流程，走 uia2 stub 或 Emulator。
4. **Chaos 套件**（E2E 之上开关）

   * 前台丢失、SQS 可见性延迟、LLM 超时重试、OCR 噪声、截图全黑/半屏遮挡。

---

# 13.C 假依赖与确定性基座

## 13.C.1 Mock LLM（确定性响应 + usage）

* 协议：`POST /chat`，入参 `{model, messages, response_format}`；出参固定 JSON 与 `usage:{prompt_tokens,completion_tokens}`。
* 根据 `messages[-1].content` 中的关键字路由不同模板，保证可预测。

> 目录：`tests/mocks/llm_server.js`（Node/Express，端口 18081）

## 13.C.2 Mock OCR & 视觉

* OCR：给定 `sha1(image_bytes)` → 从 `fixtures/ocr_map.json` 返回文本；可设置 ±5% 随机噪声（Chaos 开关）。
* 视觉：从 `fixtures/screens/*.png` 里做模板匹配；默认返回固定 bbox；Chaos 时返回偏移/不命中。

## 13.C.3 Fake Desktop UI（WeChat/评论页模拟器）

* HTTP + WebSocket 微服务，维护“侧边栏未读数、联系人列表、聊天区消息、输入框状态”。
* 动作事件：`click(x,y)` 被映射为“打开联系人/点击展开/发送按钮”等；每次动作写一个**状态转移事件**，供断言。

> 目录：`tests/fakeui/wechat_sim.py`（FastAPI），端口 18082。

## 13.C.4 Android Stub

* 用 `uiautomator2` 的 monkeypatch 接口，替换为内存状态机（不需要真机/模拟器即可跑单测/IT）。

> 目录：`tests/mocks/uia2_stub.py`

---

# 13.D 本地一键环境

`docker-compose.test.yml`

```yaml
version: "3.9"
services:
  db: { image: postgres:15, environment: { POSTGRES_USER: app, POSTGRES_PASSWORD: app, POSTGRES_DB: autoagent }, ports: ["5433:5432"] }
  redis: { image: redis:7, ports: ["6380:6379"] }
  localstack:
    image: localstack/localstack:3
    environment: { SERVICES: "sqs", DEBUG: "0" }
    ports: ["4566:4566"]
  minio:
    image: minio/minio
    command: server /data
    environment: { MINIO_ACCESS_KEY: minioadmin, MINIO_SECRET_KEY: minioadmin }
    ports: ["9000:9000"]
  api:   # 你的 server，指向上面 DB/Redis/MinIO/LocalStack
    build: ./server
    environment:
      DATABASE_URL: postgres://app:app@db:5432/autoagent
      REDIS_URL: redis://redis:6379/0
      AWS_ENDPOINT_URL: http://localstack:4566
      S3_ENDPOINT: http://minio:9000
      S3_BUCKET: wfmarket
      DEFAULT_KEY_MODE: PLAINTEXT
    depends_on: [db, redis, localstack, minio]
    ports: ["8081:8080"]
  worker:
    build: ./server
    command: node worker.js
    environment: { AWS_ENDPOINT_URL: http://localstack:4566, API_BASE: http://api:8080 }
    depends_on: [api, localstack]
  mock-llm:
    build: ./tests/mocks
    command: node llm_server.js
    ports: ["18081:18081"]
  fake-wechat:
    build: ./tests/fakeui
    command: uvicorn wechat_sim:app --host 0.0.0.0 --port 18082
    ports: ["18082:18082"]
```

> 提示：Worker 的 LLM 访问指向 `mock-llm`，通过环境开关注入（`LLM_BASE_URL=http://mock-llm:18081`）。

---

# 13.E 测试目录规划

```
tests/
├─ unit/
│  ├─ py/ (pytest)            # 引擎/动作/表达式解析
│  └─ js/ (jest)              # API/计费/市场/密钥
├─ integration/
│  ├─ worker_llm.test.js      # Worker↔Mock LLM↔SQS↔DB
│  ├─ marketplace_upload.test.js
│  └─ billing_rollup.test.js
├─ e2e/
│  ├─ desktop_wechat_e2e.py   # LP→HP 完整闭环
│  ├─ xhs_crawler_e2e.py
│  └─ android_wechat_e2e.py   # 走 uia2 stub
├─ chaos/
│  ├─ chaos_suite.py          # 注入器 + 断言
│  └─ profiles/*.yaml         # 场景参数
├─ fixtures/
│  ├─ screens/*.png
│  ├─ anchors/*.png
│  ├─ ocr_map.json
│  └─ llm_templates/*.json
```

---

# 13.F 关键用例（示例概述 + 断言）

## 13.F.1 引擎单测（pytest）

* **条件与变量**

  * 用 JSON 驱动：`@job_index < @total_jobs`，边界：负数/越界/未定义。
  * **断言**：转场落点、变量更新、错误日志（未定义变量）被捕获且不中断其他动作。
* **数据操作**

  * `get_list_item` 对空/越界抛业务错误并进入 `on_error` 分支。
* **控制流**

  * 循环 100 次无内存泄漏（对象计数）& 延迟在阈值内。

## 13.F.2 API/Jest

* **明文/加密 Key** 流程：创建→列表→管理员揭示→审计一条。
* **Marketplace 签名**：正确签名上传成功；改一字节 → 400 `bad signature`。
* **计费聚合**：插入 3 条 `llm_usage`，滚动后生成一张 `invoices`，两条 `invoice_lines`。

## 13.F.3 Worker↔SQS IT

* 送入 `llm.request.fifo`（带 `idempotency_key`），Mock LLM 返回；Worker 写 `llm_jobs/llm_usage`，并把 HP 回执发到 `device.*.hp.fifo`。
* 再次投同样 `idempotency_key`，断言 **不重复计费**，`llm_jobs.status` 为 `dedup` 或直接复用。

## 13.F.4 桌面 E2E（Fake UI）

* 启动 LP：发现未读→截图→（Mock OCR）→ `llm.submit`。
* Worker 返回→ HP `chat.send_text` → Fake UI 记录“已发送”。
* **断言**：

  * Fake UI 的消息计数 +1；
  * `run_events` 有 `ui.click / ocr.run / llm.submit / mq.ack` 序列；
  * Recorder 的快照数量在范围（例如 12–20 帧）。

## 13.F.5 Chaos

* **焦点丢失**：`focus_guard` 连续失败 3 次 → 状态转 `PAUSE`；恢复后 `RESUME` 继续下一轮。
* **SQS 延迟**：把可见性设置 1s，Worker 超时自动重试 ≤3 次。
* **OCR 噪声**：返回文本插入随机 Emoji/全角/半角，后处理仍能匹配关键信号。
* **截图全黑**：视觉模块返回“不命中”→ 触发滚动重试上限→ 进入降级策略。

---

# 13.G 可靠性与去抖（反漂移）

* **随机种子固定**：`PYTHONHASHSEED=0`、`random.seed(42)`；Node `seedrandom`。
* **时间冻结**：单测用 `freezegun`；集成测试统一 `TZ=UTC`。
* **图像断言**：用 **SSIM ≥ 0.97** 或基于锚点 bbox 的**局部相似度**，避免像素级脆弱。
* **重试与准入**：E2E 用例失败允许 **1 次重跑**；若两次失败即标记**不稳定**并阻塞发布。

---

# 13.H 指标与放行门槛（Release Gates）

* 单测覆盖率：**后端 JS ≥ 85%**；引擎 Python ≥ 90%。
* 集成 + E2E：**通过率 = 100%**（E2E 套件 8–12 条）。
* Chaos 套件核心 4 条：**通过率 ≥ 95%**；失败会阻塞合并到 `main`。
* 失败重跑后仍失败 → 创建 **P0 缺陷**并打回。
* 触发放行需上传：覆盖率报告、E2E 事件时间线、关键帧、日志到 CI Artifact。

---

# 13.I CI/CD（GitHub Actions 示例）

`.github/workflows/test.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  unit:
    runs-on: ubuntu-latest
    services:
      postgres: { image: postgres:15, env: { POSTGRES_USER: app, POSTGRES_PASSWORD: app, POSTGRES_DB: autoagent }, ports: ["5433:5432"] }
      redis: { image: redis:7, ports: ["6380:6379"] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: npm ci --prefix server
      - run: npm test --prefix server -- --coverage
      - run: pip install -r client/requirements-test.txt
      - run: pytest -q tests/unit/py --maxfail=1 --disable-warnings
      - uses: actions/upload-artifact@v4
        with: { name: coverage-server, path: server/coverage }
  integration_e2e:
    runs-on: ubuntu-latest
    needs: unit
    steps:
      - uses: actions/checkout@v4
      - run: docker compose -f docker-compose.test.yml up -d --build
      - run: npm ci --prefix tests/mocks && npm start --prefix tests/mocks &  # mock-llm 如需
      - run: pytest -q tests/integration -q
      - run: pytest -q tests/e2e -q
      - run: pytest -q tests/chaos -q || echo "::warning::Chaos failed, will mark check but block release by gate"
      - uses: actions/upload-artifact@v4
        with: { name: e2e-artifacts, path: artifacts/** }
```

> 放行门槛可用 **必需通过的 Check** + 组织级保护规则实现；Chaos 失败给 warning，但由**Gate 脚本**最终决策。

---

# 13.J 本地开发者命令（Makefile 摘要）

```makefile
seed:
\tpython scripts/seed_test_data.py
stack:
\tdocker compose -f docker-compose.test.yml up -d --build
unit:
\tnpm test --prefix server && pytest -q tests/unit/py
it:
\tpytest -q tests/integration
e2e:
\tpytest -q tests/e2e
chaos:
\tpytest -q tests/chaos -q
all: stack seed unit it e2e chaos
```

---

# 13.K 验收清单

* 一行命令 `make all` 起堆跑完整链路，生成**快照/事件/覆盖率**并成功退出。
* 任意 PR 触发 CI，E2E 全绿；改动 Worker/Actions 时，Chaos 套件仍 ≥95% 通过。
* 可从 CI Artifact 打开某次失败会话的**时间线与帧**复盘（来自阶段 12 的 `/diag` 数据）。
* Flaky 用例能被隔离且 7 天内修复率 ≥80%。

---

# 13.L 下一步（可选增强）

* **属性测试**（Hypothesis）验证动作组合对任意合法 JSON 工作流都“无崩溃”。
* **合约测试**：对外 API（/billing, /marketplace）用 Pact 合约，避免前后端/第三方变更破坏联调。
* **WebRTC 实时预览**（取代 WS 中继）在夜间构建跑 1 小时稳定性回放。
* **真机实验池**：Android Emulator Farm，跑关键 E2E 两轮做 A/B 阈值对比。

