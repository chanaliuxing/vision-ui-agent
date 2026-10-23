剪贴板一定要“**先清空、用完还原、只拿需要的**”。我整理了一份**基础动作清单**（参考 AutoHotkey/按键精灵的常见能力），并给出**最小增量实现**建议：你可以挑着加，或者一次性都加上。

---

# 一、剪贴板安全与卫生（强烈建议）

### 1) 新动作：剪贴板入栈/出栈

* `clipboard.push`：把当前剪贴板保存到内部栈中（不改现有内容）。
* `clipboard.pop`：从内部栈恢复上一个剪贴板内容（若无则清空或忽略）。
* `clipboard.clear`：清空（你已有，保留）。

> 实现（在 `Executor` 或 `WorkflowRunner` 里挂一个 `self._clip_stack: List[str]`）：

```python
# WorkflowRunner.__init__ 里
self._clip_stack = []

# run_actions 中新增
elif op == "clipboard.push":
    try:
        cur = self.exec.clipboard_get()
    except Exception:
        cur = ""
    self._clip_stack.append(cur); return

elif op == "clipboard.pop":
    prev = self._clip_stack.pop() if self._clip_stack else ""
    try:
        self.exec.clipboard_set(prev)
    except Exception:
        pass
    return
```

### 2) 升级：复制动作做“护栏”

在 `clipboard.copy_from_selection` 里增加选项：

* `pre_clear: true`：复制前清空剪贴板（避免读到旧内容）
* `trim: true`：去首尾空白
* `max_len`：超过就截断或报错
* `regex`：可选正则抽取（只留想要的部分）
* `restore_on_fail: true`：失败时恢复先前剪贴板

```python
elif op == "clipboard.copy_from_selection":
    pre_clear = bool(act.get("pre_clear", True))
    trim = bool(act.get("trim", True))
    max_len = int(act.get("max_len", 0))  # 0=无限
    regex = act.get("regex")
    save = act.get("save","copied_text")
    restore_on_fail = bool(act.get("restore_on_fail", True))

    prev = ""
    if restore_on_fail:
        try: prev = self.exec.clipboard_get()
        except: prev = ""
    if pre_clear:
        try: self.exec.clipboard_clear()
        except: pass

    # 组合键复制
    if platform.system() == "Darwin": self.exec.key_combo("command","c")
    else: self.exec.key_combo("ctrl","c")
    time.sleep(max(0, int(act.get("wait_ms", 80)))/1000.0)

    val = self.exec.clipboard_get()
    if trim: val = (val or "").strip()
    if regex:
        import re
        m = re.search(regex, val or "")
        val = m.group(1) if (m and m.groups()) else (m.group(0) if m else "")
    if max_len and len(val) > max_len:
        val = val[:max_len]

    if not val and restore_on_fail:
        try: self.exec.clipboard_set(prev)
        except: pass
    self.ctx[save] = val
    return
```

### 3) 新增：读取/写入剪贴板图片

* `clipboard.get_image` → `save: "clip_img_b64"`（PNG Base64）
* `clipboard.set_image` ← `base64: "@clip_img_b64"`

（实现时用 `PIL.ImageGrab.grabclipboard()` 读；写可用平台桥接或 fallback 走临时文件+系统命令，先给文本就好，图片可后续加。）

---

# 二、鼠标动作（补齐 AHK 常见）

* `mouse.click`（已有）
* `mouse.double_click`（你已加）
* `mouse.triple_click`：三击选整段文本常用
* `mouse.right_click`：右键
* `mouse.middle_click`：中键
* `mouse.move`：仅移动（支持 human 曲线）
* `mouse.down` / `mouse.up`（你已加）
* `mouse.drag`（已加）
* `mouse.wheel`：垂直滚动；可选 `axis: "h"` 水平滚动
* `mouse.click_at_offset`：相对某个 `bbox` 的偏移点击（列表项右上角等）

示例分支（放入 `run_actions`）：

```python
elif op == "mouse.triple_click":
    btn = (act.get("button") or "left").lower()
    x, y = int(act.get("x")), int(act.get("y"))
    self.exec.click(x, y, button=btn); self.exec.click(x, y, button=btn); self.exec.click(x, y, button=btn); return

elif op == "mouse.right_click":
    x, y = int(act.get("x")), int(act.get("y"))
    self.exec.click(x, y, button="right"); return

elif op == "mouse.middle_click":
    x, y = int(act.get("x")), int(act.get("y"))
    self.exec.click(x, y, button="middle"); return

elif op == "mouse.move":
    # 支持 human_path=true
    human = bool(act.get("human", True))
    x, y = int(act.get("x")), int(act.get("y"))
    if human: self._human_move_and_click(x, y, button=None)  # 改下内部函数，button=None时只移动不点
    else: self.exec.move_to(x, y, duration=float(act.get("duration_s", 0.0)))
    return

elif op == "mouse.wheel":
    amt = int(act.get("amount", -400))
    axis = (act.get("axis") or "v").lower()
    if axis.startswith("h"):
        try:
            import pyautogui as _pag
            _pag.hscroll(amt)
        except Exception:
            pass
    else:
        self.exec.scroll(amt)
    return

elif op == "mouse.click_at_offset":
    tgt = act.get("target") or {}
    off = act.get("offset") or [0,0]
    btn = (act.get("button") or "left").lower()
    # 解析 bbox → 中心 → 加偏移
    ref = None
    if tgt.get("bbox_var"): ref = self._get_var_value(tgt.get("bbox_var"))
    ref = ref or tgt.get("bbox")
    def _center(b):
        if isinstance(b, dict): return int(b.get("x",0)+b.get("w",0)/2), int(b.get("y",0)+b.get("h",0)/2)
        if isinstance(b,(list,tuple)) and len(b)>=4:
            x1,y1,x2,y2=b[:4]; return int((x1+x2)/2), int((y1+y2)/2)
        return None
    cen = _center(ref)
    if not cen: raise RuntimeError("mouse.click_at_offset 需要 target bbox/bbox_var")
    x = int(cen[0] + int(off[0] or 0)); y = int(cen[1] + int(off[1] or 0))
    human = bool(act.get("human", True))
    if human: self._human_move_and_click(x, y, button=btn)
    else: self.exec.click(x, y, button=btn)
    return
```

> 注：把你的人类轨迹函数 `_human_move_and_click` 微调一下，`button=None` 时只移动不点击。

---

# 三、键盘动作（补齐 AHK 常见）

* `keyboard.key`（单键）
* `keyboard.key_down` / `keyboard.key_up`
* `keyboard.sequence`：发送一串键，支持间隔与修饰键
* `keyboard.type_text`（已有，人类模式亦可）
* `keyboard.select_all`：平台兼容 `Cmd/Ctrl+A`
* `keyboard.cut`：`Cmd/Ctrl+X`
* `keyboard.copy`：`Cmd/Ctrl+C`（与剪贴板动作不同：这里不读剪贴板，只发按键）
* `keyboard.paste`：`Cmd/Ctrl+V`
* `keyboard.toggle_ime`：切换中英文（mac: `Ctrl+Space`；Win 可配）

示例分支：

```python
elif op == "keyboard.key_down":
    self.exec.key_down(act.get("key")); return
elif op == "keyboard.key_up":
    self.exec.key_up(act.get("key")); return
elif op == "keyboard.sequence":
    seq = act.get("keys") or []  # 例: ["ctrl","shift","p"] 或 ["enter","tab","tab"]
    interval_ms = int(act.get("interval_ms", 50))
    for k in seq:
        self.exec.key(k)
        time.sleep(max(0, interval_ms)/1000.0)
    return
elif op == "keyboard.select_all":
    if platform.system()=="Darwin": self.exec.key_combo("command","a")
    else: self.exec.key_combo("ctrl","a")
    return
elif op == "keyboard.copy":
    if platform.system()=="Darwin": self.exec.key_combo("command","c")
    else: self.exec.key_combo("ctrl","c")
    return
elif op == "keyboard.cut":
    if platform.system()=="Darwin": self.exec.key_combo("command","x")
    else: self.exec.key_combo("ctrl","x")
    return
elif op == "keyboard.paste":
    if platform.system()=="Darwin": self.exec.key_combo("command","v")
    else: self.exec.key_combo("ctrl","v")
    return
elif op == "keyboard.toggle_ime":
    # 默认 mac: Ctrl+Space; Windows: Shift+Alt (可通过 vars 覆盖)
    kseq = (_get_wf(self).get("vars") or {}).get("toggle_ime_keys")
    if not kseq:
        kseq = ["ctrl","space"] if platform.system()=="Darwin" else ["shift","alt"]
    self.exec.key_combo(*kseq)
    return
```

> `Executor` 里补齐 `key_down/key_up`（pyautogui 的 `keyDown/keyUp`）。

---

# 四、窗口/应用与系统通用

* `window.focus_by_title`：按标题（或包含）聚焦
* `window.minimize` / `window.close` / `window.move_resize`
* `os.activate_app` / `os.launch_app`（你已增强多别名）
* `window.wait_title`：等待某窗口标题出现（配超时）
* `os.shell`：执行命令行，保存 stdout/stderr/exitcode 到 ctx
* `os.download`：从 URL 下载到文件（可后加）

最小实现建议：

* Mac 用 `osascript` 做标题匹配；Windows 用 `powershell + UIAutomation` 或第三方库，先给“应用级”足够了。
* `os.shell` 用 `subprocess.run(capture_output=True)`

```python
elif op == "os.shell":
    cmd = act.get("cmd")
    shell = bool(act.get("shell", True))
    timeout = int(act.get("timeout_s", 20))
    save = act.get("save", "shell")
    import subprocess, shlex
    if isinstance(cmd, str) and not shell:
        cmd = shlex.split(cmd)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=timeout)
        self.ctx[save] = {"code": p.returncode, "out": p.stdout, "err": p.stderr}
    except Exception as e:
        self.ctx[save] = {"code": -1, "out": "", "err": str(e)}
    return
```

---

# 五、文件/目录基础（再补几项）

* `os.mkdir`：创建目录（递归）
* `os.remove`：删除文件
* `os.copy` / `os.move`：文件复制/移动
* `os.listdir`：列目录（支持 glob/过滤），保存到 ctx
* `os.read_json` / `os.write_json`：JSON 读写
* `os.read_yaml` / `os.write_yaml`：YAML（可选）

（这些都很直白，就不一一贴代码了；你可沿用 `read_text_file/write_text_file` 的风格。）

---

# 六、示例：**安全复制→粘贴→写盘**的一条龙

```json
{
  "actions": [
    { "do": "clipboard.push" },                  // 保存现场
    { "do": "clipboard.clear" },                 // 清空
    { "do": "mouse.double_click", "target": {"bbox_var": "@title_bbox"} },
    { "do": "clipboard.copy_from_selection", "save": "title", "trim": true, "regex": "^(.*)$", "max_len": 200 },
    { "do": "instr.click", "target": {"selector": "#input"}, "human_click": true },
    { "do": "clipboard.paste", "text": "@title" },
    { "do": "os.write_file", "path": "out/titles/last.txt", "content": "@title", "mkdirs": true },
    { "do": "clipboard.pop" }                    // 恢复现场
  ],
  "on_success": "next"
}
```

---

# 七、建议的 `vars` 默认（可放 workflow\.json）

```json
"vars": {
  "prefer_human_input": true,
  "human_mouse": { "speed_px_per_s": 1200, "steps": 34, "overshoot_px": 6, "jitter_px": 2 },
  "human_type_interval_ms": 60,
  "toggle_ime_keys": ["ctrl","space"],   // mac 缺省；Windows 可写 ["shift","alt"]
  "danger_words": ["publish","delete","pay","submit","确认","发布","删除","支付","提交"]
}
```


