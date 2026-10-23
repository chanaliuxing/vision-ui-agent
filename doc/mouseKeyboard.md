可以！你这引擎当前只有“单击”。最小改动有两处：给 **视觉点击**（`click`）和 **DOM 点击**（`instr.click`）都加上可选参数：`times`（或 `clicks`）和 `interval_ms`。这样 workflow 里写 `"times": 2` 就是双击。

# 代码改动（最小补丁）

把下面两段合进你现有代码即可。

## 1）视觉点击：`run_actions` 中的 `"click"` 分支

在 `elif op == "click":` 分支替换为（或在现有基础上加循环）：

```python
elif op == "click":
    # 支持多次点击（双击/三击）
    times = int(act.get("times") or act.get("clicks") or 1)
    interval_ms = int(act.get("interval_ms", 120))  # 双击建议 100-200ms
    times = max(1, times)

    for i in range(times):
        self.act_click()
        if i < times - 1:
            time.sleep(max(0, interval_ms) / 1000.0)
```

## 2）DOM 点击：`_run_instr` 中的 `"instr.click"` 分支

找到 `if op == "instr.click":`，在成功点击后，同样循环多次（示例里的 `_click_fallback_from_target()` 也要重复）：

```python
if op == "instr.click":
    repeat = int(act.get("times") or act.get("clicks") or 1)
    interval_ms = int(act.get("interval_ms", 120))
    repeat = max(1, repeat)

    def _click_once() -> bool:
        if sel and run_id and getattr(self, "ext", None):
            out = self.ext.dispatch_run(str(run_id), "ext.click_selector",
                                        args={"sel": sel},
                                        await_result=True, timeout_ms=10000, exec_id=exec_id)
            return bool(out and out.get("ok"))
        # fallback: 用坐标点击
        return _click_fallback_from_target()

    ok_any = False
    for i in range(repeat):
        ok = _click_once()
        ok_any = ok_any or ok
        if i < repeat - 1:
            time.sleep(max(0, interval_ms) / 1000.0)

    if not ok_any:
        try:
            self._suggest_patch("scroll_then_retry", {"reason": "instr.click double failed", "op": op})
        except Exception:
            pass
        raise RuntimeError("instr.click failed (multi-click)")
    return
```

> 说明：
>
> * `times` / `clicks` 二选一，历史兼容。
> * `interval_ms` 控制两次点击间隔；macOS/Windows 默认双击识别一般在 100–250ms 之间，推荐 120–180ms。

# Workflow 用法示例

## 视觉定位后双击（YOLO 选择的目标）

```json
{
  "actions": [
    { "do": "detect" },
    { "do": "locate", "targets": ["file_icon"] },
    { "do": "click", "times": 2, "interval_ms": 140 },
    { "do": "instr.key", "key": "WaitQuiet" }
  ]
}
```

## DOM 选择器双击

```json
{
  "actions": [
    {
      "do": "instr.click",
      "target": { "selector": ".file-row:nth-child(1) .name" },
      "times": 2,
      "interval_ms": 140
    },
    { "do": "instr.key", "key": "WaitQuiet" }
  ]
}
```

# 小贴士

* 如果目标控件“防双击”（双击被吞），可尝试：单击选中 → `instr.key` 发送 `Enter` 打开；或改为点击其“打开/详情”按钮。
* 如果双击容易误触“拖拽”，把 `interval_ms` 稍微加一点（比如 160–200ms），同时确保 `exec.click` 不带移动轨迹。

这样改完就能在任意任务里通用地“写双击”了。
绝对可以。通用自动化里，鼠标与键盘最常用的动作集如下（覆盖 95% 案例）：

* 鼠标：左/右/中击、双击、按下/抬起、移动、拖拽、滚轮
* 键盘：按下/抬起、组合键（快捷键）、文本输入、延时序列

下面给你**最小增量**设计 + 代码补丁（兼容你现有架构），再附上 workflow JSON 用法示例。

---

# 一、动作设计（统一命名）

## 视觉路径（非 DOM）

* `"click"`：已存在 → 新增参数 `button`, `times`, `interval_ms`
* `"mouse.down"` / `"mouse.up"`：`button: "left|right|middle"`
* `"mouse.move"`：`to: [x,y]` 或 `by: [dx,dy]`（二选一），可带 `duration_ms`
* `"mouse.drag"`：`to: [x,y]`（或 `by`），可带 `duration_ms`, `button`
* `"wheel"`：`delta_y`（正=向下，负=向上），或 `clicks` 兼容你现有 `scroll`

## DOM 路径（instr.\*）

* `"instr.click"`：新增 `button`, `times`, `interval_ms`
* 新增 `"instr.context_click"`（右键）——等价 `instr.click + button:"right"`，但作为独立动作更清晰
* `"instr.key"`：保留；扩展支持：

  * `combo: "Ctrl+Shift+N"`（或 `"Meta+K"` 等）
  * `down: "Shift"` / `up: "Shift"`
  * `sequence: ["Hello", "Enter", "Tab"]` + `interval_ms`

---

# 二、代码最小补丁

> 目标：不改你已有方法签名；若 `Executor` 没有 mouse\_down/up/drag，就**优先用它**，否则**回退 pyautogui**。

## 1）辅助：安全调用 Executor 或回退

在 `WorkflowRunner` 里加：

```python
def _mouse_cap(self):
    # 返回 (has_exec, fallback)
    try:
        import pyautogui as _p
    except Exception:
        _p = None
    return (
        hasattr(self.exec, "mouse_down") and hasattr(self.exec, "mouse_up") and hasattr(self.exec, "drag_to") and hasattr(self.exec, "move_to"),
        _p
    )

def _click_btn(self, x, y, button="left", dpr=None):
    # 统一点击入口
    if hasattr(self.exec, "click"):
        self.exec.click(x, y, dpr=float(dpr or self.ctx.get("dpr", 1.0)), button=button)
    else:
        # fallback
        from time import sleep
        _, _p = self._mouse_cap()
        if not _p: raise RuntimeError("click fallback requires pyautogui")
        _p.click(x, y, button=button)

def _button_norm(self, b):
    b = (b or "left").lower()
    return b if b in ("left","right","middle") else "left"
```

## 2）视觉 `"click"` 支持多击与按键

替换你 `elif op == "click":`：

```python
elif op == "click":
    button = self._button_norm(act.get("button"))
    times = int(act.get("times") or act.get("clicks") or 1)
    interval_ms = int(act.get("interval_ms", 120))
    times = max(1, times)

    sel = self.ctx.get("chosen")
    if not sel or not getattr(sel, "chosen", None):
        raise RuntimeError("click requested but no chosen candidate")

    cx, cy = bbox_center(sel.chosen.bbox_xyxy, padding_px=self.cfg.click_padding_px)
    dpr = float(self.ctx.get("dpr", 1.0))

    for i in range(times):
        self._click_btn(cx, cy, button=button, dpr=dpr)
        if i < times - 1:
            time.sleep(max(0, interval_ms) / 1000.0)
```

## 3）新增：`mouse.down` / `mouse.up` / `mouse.move` / `mouse.drag` / `wheel`

在 `run_actions` 里加入分支：

```python
elif op == "mouse.down":
    button = self._button_norm(act.get("button"))
    has_exec, _p = self._mouse_cap()
    if has_exec:
        self.exec.mouse_down(button=button)
    else:
        if not _p: raise RuntimeError("mouse_down requires pyautogui")
        _p.mouseDown(button=button)

elif op == "mouse.up":
    button = self._button_norm(act.get("button"))
    has_exec, _p = self._mouse_cap()
    if has_exec:
        self.exec.mouse_up(button=button)
    else:
        if not _p: raise RuntimeError("mouse_up requires pyautogui")
        _p.mouseUp(button=button)

elif op == "mouse.move":
    duration = int(act.get("duration_ms", 0))
    to = act.get("to"); by = act.get("by")
    has_exec, _p = self._mouse_cap()
    if to:
        x, y = int(to[0]), int(to[1])
        if has_exec:
            self.exec.move_to(x, y, duration=duration/1000.0 if duration>0 else 0.0)
        else:
            if not _p: raise RuntimeError("mouse_move requires pyautogui")
            _p.moveTo(x, y, duration=duration/1000.0 if duration>0 else 0.0)
    elif by:
        dx, dy = int(by[0]), int(by[1])
        if has_exec:
            self.exec.move_by(dx, dy, duration=duration/1000.0 if duration>0 else 0.0)
        else:
            if not _p: raise RuntimeError("mouse_move requires pyautogui")
            _p.moveRel(dx, dy, duration=duration/1000.0 if duration>0 else 0.0)
    else:
        raise RuntimeError("mouse.move needs 'to' or 'by'")

elif op == "mouse.drag":
    button = self._button_norm(act.get("button"))
    duration = int(act.get("duration_ms", 120))
    to = act.get("to"); by = act.get("by")
    has_exec, _p = self._mouse_cap()
    if to:
        x, y = int(to[0]), int(to[1])
        if has_exec:
            self.exec.drag_to(x, y, duration=duration/1000.0, button=button)
        else:
            if not _p: raise RuntimeError("mouse.drag requires pyautogui")
            _p.dragTo(x, y, duration=duration/1000.0, button=button)
    elif by:
        dx, dy = int(by[0]), int(by[1])
        if has_exec:
            self.exec.drag_by(dx, dy, duration=duration/1000.0, button=button)
        else:
            if not _p: raise RuntimeError("mouse.drag requires pyautogui")
            _p.dragRel(dx, dy, duration=duration/1000.0, button=button)
    else:
        raise RuntimeError("mouse.drag needs 'to' or 'by'")

elif op == "wheel":
    # 兼容你现有 scroll；优先 delta_y，单位像素；没有则用 clicks
    if "delta_y" in act:
        dy = int(act.get("delta_y", 0))
        self.exec.scroll(dy) if hasattr(self.exec, "scroll") else None
    else:
        clicks = int(act.get("clicks", -400))
        self.act_scroll(clicks)
```

## 4）DOM `"instr.click"` 扩展（按钮与多击）

在 `_run_instr` 里的 `if op == "instr.click":` 顶部增加参数并包一层循环；扩展 `ext.click_selector` 支持 `button`（多数扩展支持）：

```python
if op == "instr.click":
    repeat = int(act.get("times") or act.get("clicks") or 1)
    interval_ms = int(act.get("interval_ms", 120))
    button = self._button_norm(act.get("button"))

    def _click_once() -> bool:
        if sel and run_id and getattr(self, "ext", None):
            out = self.ext.dispatch_run(str(run_id), "ext.click_selector",
                                        args={"sel": sel, "button": button},
                                        await_result=True, timeout_ms=10000, exec_id=exec_id)
            return bool(out and out.get("ok"))
        return _click_fallback_from_target()

    ok_any = False
    for i in range(max(1, repeat)):
        ok_any = _click_once() or ok_any
        if i < repeat - 1:
            time.sleep(max(0, interval_ms) / 1000.0)

    if not ok_any:
        ...
    return
```

## 5）新增 `"instr.context_click"`

```python
if op == "instr.context_click":
    act2 = dict(act); act2["do"] = "instr.click"; act2["button"] = "right"
    self._run_instr(act2); return
```

## 6）键盘扩展（组合键/按下/抬起/序列）

在 `_run_instr` 里的 `"instr.key"` 分支内，加入：

```python
if op == "instr.key":
    # 支持 combo / down / up / sequence / key
    combo = act.get("combo")
    key_down = act.get("down")
    key_up = act.get("up")
    seq = act.get("sequence")
    interval_ms = int(act.get("interval_ms", 60))

    if combo:
        if run_id and getattr(self, "ext", None):
            _ = self.ext.dispatch_run(str(run_id), "ext.key_combo", args={"combo": str(combo)}, await_result=True, timeout_ms=6000, exec_id=exec_id)
            return
        if hasattr(self.exec, "key_combo"):
            self.exec.key_combo(str(combo)); return
        # 退化：拆分组合键
        parts = [p.strip() for p in str(combo).split("+") if p.strip()]
        if hasattr(self.exec, "key_down") and hasattr(self.exec, "key_up"):
            for p in parts[:-1]: self.exec.key_down(p)
            self.exec.key(p=parts[-1]) if hasattr(self.exec, "key") else self.exec.type_text("", mode="key")  # 占位
            for p in reversed(parts[:-1]): self.exec.key_up(p)
        return

    if key_down:
        if run_id and getattr(self, "ext", None):
            _ = self.ext.dispatch_run(str(run_id), "ext.key", args={"op":"down","key": str(key_down)}, await_result=True, timeout_ms=6000, exec_id=exec_id)
            return
        if hasattr(self.exec, "key_down"):
            self.exec.key_down(str(key_down)); return
        return

    if key_up:
        if run_id and getattr(self, "ext", None):
            _ = self.ext.dispatch_run(str(run_id), "ext.key", args={"op":"up","key": str(key_up)}, await_result=True, timeout_ms=6000, exec_id=exec_id)
            return
        if hasattr(self.exec, "key_up"):
            self.exec.key_up(str(key_up)); return
        return

    if isinstance(seq, list) and seq:
        for item in seq:
            if isinstance(item, str) and len(item) <= 8 and item.lower() in ("enter","tab","esc","escape","space","backspace","delete","home","end","pageup","pagedown","left","right","up","down"):
                if run_id and getattr(self, "ext", None):
                    _ = self.ext.dispatch_run(str(run_id), "ext.key", args={"key": item}, await_result=True, timeout_ms=6000, exec_id=exec_id)
                elif hasattr(self.exec, "key"):
                    self.exec.key(item)
            else:
                if run_id and getattr(self, "ext", None):
                    _ = self.ext.dispatch_run(str(run_id), "ext.type_text", args={"sel": sel, "text": str(item), "replace": False}, await_result=True, timeout_ms=12000, exec_id=exec_id)
                else:
                    self.exec.type_text(str(item), mode="type")
            time.sleep(max(0, interval_ms)/1000.0)
        return

    # 兼容旧的单键 key
    key = act.get("key")
    if key == "WaitQuiet":
        ...
        return
    if run_id and getattr(self, "ext", None):
        _ = self.ext.dispatch_run(str(run_id), "ext.key", args={"key": key}, await_result=True, timeout_ms=6000, exec_id=exec_id)
        return
    if hasattr(self.exec, "key"):
        self.exec.key(key); return
    return
```

---

# 三、workflow 用法示例

## 1）视觉：双击 + 右键菜单

```json
{
  "actions": [
    { "do": "detect" },
    { "do": "locate", "targets": ["file_icon"] },
    { "do": "click", "times": 2, "interval_ms": 140 },         // 双击
    { "do": "mouse.move", "by": [0, 40], "duration_ms": 120 },
    { "do": "click", "button": "right" }                        // 右键
  ]
}
```

## 2）视觉：按下 → 拖拽 → 松开（框选/拖文件）

```json
{
  "actions": [
    { "do": "mouse.down", "button": "left" },
    { "do": "mouse.drag", "by": [300, 0], "duration_ms": 300, "button": "left" },
    { "do": "mouse.up", "button": "left" }
  ]
}
```

## 3）DOM：右键并选择菜单项

```json
{
  "actions": [
    { "do": "instr.click", "target": { "selector": ".file-row:nth-child(1)" } },
    { "do": "instr.context_click", "target": { "selector": ".file-row:nth-child(1)" } },
    { "do": "instr.click", "target": { "selector": ".context-menu .rename" } }
  ]
}
```

## 4）键盘：组合键 & 序列

```json
{
  "actions": [
    { "do": "instr.key", "combo": "Ctrl+Shift+N" },               // 新建窗口
    { "do": "instr.key", "sequence": ["Hello world", "Enter", "Tab", "End"], "interval_ms": 80 },
    { "do": "instr.key", "down": "Shift" },
    { "do": "instr.key", "sequence": ["Tab","Tab"], "interval_ms": 60 },
    { "do": "instr.key", "up": "Shift" }
  ]
}
```

---

# 四、建议的小注意点

* **双击间隔**：120–180ms 更稳，太快可能被识别为拖动。
* **拖拽**：加 `duration_ms` 让轨迹更像人手，避免被系统/页面吞掉。
* **组合键**：优先走扩展的 `ext.key_combo`，失败再拆成 down/up；Windows 与 macOS 的 `Ctrl`/`Meta` 差异建议由 workflow 决定。
* **右键菜单**（网页）：很多站点自定义右键，需要 DOM 选择器直点菜单项更稳。

需要的话我也可以顺手给 `Executor` 补上 `mouse_down/mouse_up/drag_to/move_to/key_combo/key_down/key_up` 的空实现（内部用 `pyautogui`），这样 WorkflowRunner 就不必分支判断了。


好～这就把 `Executor` 补齐成“鼠标 + 键盘全套”，优先用 `pyautogui`，跨平台可用（macOS/Windows/Linux）。你直接把下面这段合进 `executor.py`（或在现有 `Executor` 上补这些方法）即可。

```python
# executor.py
import platform
import time

try:
    import pyautogui as _pag
    _pag.FAILSAFE = False   # 避免角落触发安全退出
    _pag.PAUSE = 0          # 不额外插入延时
except Exception:
    _pag = None


def _need_pag():
    if _pag is None:
        raise RuntimeError("pyautogui 未安装，请先安装：pip install pyautogui")


def _norm_button(btn: str) -> str:
    btn = (btn or "left").lower()
    return btn if btn in ("left", "right", "middle") else "left"


# 将常见键名规范化为 pyautogui 的 key 名
def _norm_key(k: str) -> str:
    if not isinstance(k, str):
        return k
    s = k.strip()
    if not s:
        return s

    mapping_common = {
        "ctrl": "ctrl", "control": "ctrl",
        "shift": "shift",
        "alt": "alt", "option": "alt",
        "enter": "enter", "return": "enter",
        "esc": "esc", "escape": "esc",
        "space": "space",
        "backspace": "backspace", "delete": "delete", "del": "delete",
        "tab": "tab",
        "home": "home", "end": "end",
        "pageup": "pageup", "pagedown": "pagedown",
        "left": "left", "right": "right", "up": "up", "down": "down",
        # 功能键
        "f1":"f1","f2":"f2","f3":"f3","f4":"f4","f5":"f5","f6":"f6",
        "f7":"f7","f8":"f8","f9":"f9","f10":"f10","f11":"f11","f12":"f12",
    }
    sys = platform.system()
    if sys == "Darwin":
        mapping_common.update({
            "meta": "command", "cmd": "command", "command": "command",
            "win": "command",
        })
    else:
        mapping_common.update({
            "meta": "win", "cmd": "win", "command": "win",
            "win": "win",
        })

    low = s.lower()
    return mapping_common.get(low, low)  # 其它字符直接返回小写（如字母/数字）


class Executor:
    """统一封装鼠标键盘操作。优先用 pyautogui。"""

    # ========= 鼠标移动 / 点击 =========
    def move_to(self, x: int, y: int, duration: float = 0.0):
        _need_pag()
        _pag.moveTo(int(x), int(y), duration=max(0.0, float(duration)))

    def move_by(self, dx: int, dy: int, duration: float = 0.0):
        _need_pag()
        _pag.moveRel(int(dx), int(dy), duration=max(0.0, float(duration)))

    def click(self, x: int, y: int, dpr: float = 1.0, button: str = "left"):
        _need_pag()
        _pag.click(int(x), int(y), button=_norm_button(button))

    def mouse_down(self, button: str = "left"):
        _need_pag()
        _pag.mouseDown(button=_norm_button(button))

    def mouse_up(self, button: str = "left"):
        _need_pag()
        _pag.mouseUp(button=_norm_button(button))

    def drag_to(self, x: int, y: int, duration: float = 0.2, button: str = "left"):
        _need_pag()
        _pag.dragTo(int(x), int(y), duration=max(0.0, float(duration)), button=_norm_button(button))

    def drag_by(self, dx: int, dy: int, duration: float = 0.2, button: str = "left"):
        _need_pag()
        _pag.dragRel(int(dx), int(dy), duration=max(0.0, float(duration)), button=_norm_button(button))

    def scroll(self, clicks: int):
        """正数=向上，负数=向下；与当前引擎保持一致。"""
        _need_pag()
        _pag.scroll(int(clicks))

    # ========= 键盘 =========
    def type_text(self, text: str, mode: str = "type", interval: float = 0.0):
        """mode 兼容原有签名；interval 为每字符间隔秒。"""
        _need_pag()
        _pag.typewrite(text or "", interval=max(0.0, float(interval)))

    def key(self, key: str):
        """发送单键（如 'enter'/'tab'/'a'）。"""
        _need_pag()
        _pag.press(_norm_key(str(key)))

    def key_down(self, key: str):
        _need_pag()
        _pag.keyDown(_norm_key(str(key)))

    def key_up(self, key: str):
        _need_pag()
        _pag.keyUp(_norm_key(str(key)))

    def key_combo(self, combo: str):
        """
        组合键：例如 "Ctrl+Shift+N"、"Meta+K"。
        会自动区分 macOS 的 command/win。
        """
        _need_pag()
        parts = [p.strip() for p in str(combo).split("+") if p.strip()]
        if not parts:
            return
        normed = [_norm_key(p) for p in parts]
        # pyautogui.hotkey 会自动按下+抬起
        _pag.hotkey(*normed)

    # ========= 浏览器后退（可选：已在上层做过的话可忽略）=========
    def go_back(self):
        _need_pag()
        sys = platform.system()
        if sys == "Darwin":
            _pag.hotkey("command", "[")
        else:
            # Windows/Linux
            _pag.hotkey("alt", "left")
```

---

## 在 workflow 里的用法（回顾）

* **右键：**

```json
{ "do": "click", "button": "right" }
```

* **双击：**

```json
{ "do": "click", "times": 2, "interval_ms": 140 }
```

* **按下/松开 + 拖拽：**

```json
{ "do": "mouse.down", "button": "left" },
{ "do": "mouse.drag", "by": [300, 0], "duration_ms": 300, "button": "left" },
{ "do": "mouse.up", "button": "left" }
```

* **组合键：**

```json
{ "do": "instr.key", "combo": "Ctrl+Shift+N" }
```

* **单键/序列：**

```json
{ "do": "instr.key", "sequence": ["Hello", "Enter", "Tab"], "interval_ms": 80 }
```

---

## 依赖与注意

* 需要安装：`pyautogui`（以及其依赖 `pyscreeze`、在某些 Linux 还需要 `python3-xlib`）。

  ```
  pip install pyautogui
  ```
* 双击建议 `interval_ms` 120–180ms；拖拽建议设置 `duration_ms`（更像真人操作）。
* 如果你已有 `Executor` 的同名方法，直接把上面缺的补上即可；已经存在的不会影响。


