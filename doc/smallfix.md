我给你一套“最小侵入 + 高可配”的补丁，把**危险词 / loading\&toast 词表 / OCR 长度阈值 / 签名权重与尺寸 / 浏览器与 app 多别名**等都做成 **workflow\.vars → 环境变量 → 默认值** 的优先级链。你可以逐段拷进去；如果某些辅助函数（例如你提到的 `_to_name_list` / `_any_true`）不在你当前文件里，我也附了**安全兜底实现**。

---

# 1) 通用配置读取辅助（放在 `WorkflowRunner` 顶部位置，类外）

```python
# ---- config helpers (global) ----
import os

def _get_wf(self):
    try:
        return self.workflow if isinstance(self.workflow, dict) else {}
    except Exception:
        return {}

def _wf_var(self, key, default=None):
    try:
        return (_get_wf(self).get("vars") or {}).get(key, default)
    except Exception:
        return default

def _wf_list(self, key, default=None):
    v = _wf_var(self, key, None)
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        xs = [x.strip() for x in v.split(",") if x.strip()]
        return xs or (default or [])
    return default or []

def _env_list(name, default=None):
    s = os.getenv(name)
    if not s:
        return default or []
    xs = [x.strip() for x in s.split(",") if x.strip()]
    return xs or (default or [])

def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_bool(name, default=False):
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1","true","yes","y","on")
```

> 有了这些，你可以统一从 `workflow.vars` 与环境变量读取配置；任何缺失用默认。

---

# 2) 危险词可配（在 `act_click` 里改“危险双确认”段）

把你现有：

```python
if os.getenv("DANGER_DOUBLE_CONFIRM", "1") != "0":
    words = [w.strip() for w in (os.getenv("DANGER_WORDS", "发布,删除,支付,提交").split(",")) if w.strip()]
```

改为：

```python
if _env_bool("DANGER_DOUBLE_CONFIRM", True):
    # 优先 workflow.vars.danger_words，其次 env DANGER_WORDS，最后默认中英混合词
    default_words = ["publish","delete","pay","submit","确认","发布","删除","支付","提交"]
    words = _wf_list(self, "danger_words") or _env_list("DANGER_WORDS", default_words)
```

---

# 3) OCR token 长度阈值可配（在 `_ocr_tokens_current`）

把原来的硬编码 `2 <= len(s) <= 16` 改为：

```python
def _ocr_tokens_current(self) -> List[str]:
    toks: List[str] = []
    try:
        if hasattr(self, "ocr") and self.ocr:
            min_len = _env_int("OCR_TOKEN_MIN_LEN", _env_int("WF_OCR_TOKEN_MIN_LEN", 2))
            max_len = _env_int("OCR_TOKEN_MAX_LEN", _env_int("WF_OCR_TOKEN_MAX_LEN", 16))
            got = self.ocr.read_texts(self.ctx.get("last_pil")) or []
            for t in got:
                s = (t or "").strip()
                if min_len <= len(s) <= max_len:
                    toks.append(s)
    except Exception:
        pass
    return toks
```

> 兼容两套名字：`OCR_TOKEN_MIN_LEN/MAX_LEN` 或 `WF_OCR_TOKEN_MIN_LEN/MAX_LEN`。

---

# 4) loading/toast 词表可配（在 `_detect_loading_toast`）

将你函数里两处 `loading_words/toast_words` 替换为：

```python
loading_words = _wf_list(self, "loading_words") or _env_list("WF_LOADING_WORDS", ["加载","loading","处理中","正在","刷新"])
toast_words   = _wf_list(self, "toast_words")   or _env_list("WF_TOAST_WORDS",   ["成功","已发布","完成","保存","已复制","success","saved","done"])
```

并把英文匹配与小写化保持（你已有 `toks_join.lower()`）。

---

# 5) 签名权重与参数可配（在 `_sig_sim` 与 `_signature`）

### `_sig_sim` 读取权重（默认不变）

```python
@staticmethod
def _sig_sim(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    # tiles + yolo_hist + layout
    w1 = _env_float("WF_SIG_W_TILES", 0.4)
    w2 = _env_float("WF_SIG_W_YOLO",  0.4)
    w3 = _env_float("WF_SIG_W_LAYOUT",0.2)
    total = max(1e-9, w1 + w2 + w3)
    w1, w2, w3 = w1/total, w2/total, w3/total

    ph_a = a.get("phash_tiles", []); ph_b = b.get("phash_tiles", [])
    ph_len = max(1, min(len(ph_a), len(ph_b)))
    ph_eq = sum(1 for x, y in zip(ph_a, ph_b) if x == y) / ph_len

    keys = set(a.get("yolo_hist", {})) | set(b.get("yolo_hist", {}))
    va = [a.get("yolo_hist", {}).get(k, 0) for k in keys]
    vb = [b.get("yolo_hist", {}).get(k, 0) for k in keys]
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    yo = (dot / (na * nb)) if na * nb else 0.0

    lay_a = a.get("layout"); lay_b = b.get("layout")
    if isinstance(lay_a, str) and isinstance(lay_b, str) and len(lay_a) == len(lay_b) and len(lay_a) > 0:
        h_eq = sum(1 for x, y in zip(lay_a, lay_b) if x == y) / len(lay_a)
    else:
        h_eq = 0.0
    return w1 * ph_eq + w2 * yo + w3 * h_eq
```

### `_tile_hashes` / `_signature` 参数化

* 让 tile 数量和 layout 网格大小、OCR top 数量都可配。

```python
@staticmethod
def _tile_hashes(bgr: np.ndarray, tiles: int = None) -> List[str]:
    if tiles is None:
        tiles = _env_int("WF_SIG_TILE_COUNT", 4)
    try:
        small = cv2.resize(bgr, (128, 128))
    except Exception:
        small = bgr
    hlist: List[str] = []
    t = int(math.sqrt(tiles)) if tiles > 0 else 1
    t = max(1, t)
    th, tw = small.shape[0] // t, small.shape[1] // t
    for i in range(t):
        for j in range(t):
            tile = small[i * th : (i + 1) * th, j * tw : (j + 1) * tw]
            h = hashlib.sha1(tile.tobytes()).hexdigest()
            hlist.append(h)
    return hlist[:tiles]

def _signature(self, bgr: np.ndarray, dets: List[Any]) -> Dict[str, Any]:
    # layout 网格
    grid = _env_int("WF_SIG_LAYOUT_GRID", 16)  # 16x16
    sig = {"phash": self._phash(bgr),
           "phash_tiles": self._tile_hashes(bgr, tiles=_env_int("WF_SIG_TILE_COUNT", 4)),
           "yolo_hist": self._yolo_hist(dets)}
    try:
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(g, (grid, grid), interpolation=cv2.INTER_AREA)
        blocks = (small.reshape(grid, grid) > small.mean()).astype(np.uint8).flatten()
        sig["layout"] = ''.join('1' if x else '0' for x in blocks.tolist())
    except Exception:
        pass
    # URL hint...
    try:
        url = self._get_url_hint()
        if url:
            sig["url"] = url
    except Exception:
        pass
    # Top OCR tokens 可配
    try:
        if hasattr(self, "ocr") and self.ocr:
            toks = self.ocr.read_texts(self.ctx.get("last_pil")) or []
            min_len = _env_int("OCR_TOKEN_MIN_LEN", 2)
            max_len = _env_int("OCR_TOKEN_MAX_LEN", 12)
            toks = [t.strip() for t in toks if t and min_len <= len(t.strip()) <= max_len]
            toks = sorted(set(toks))[:_env_int("WF_SIG_OCR_TOPK", 8)]
            sig["ocr_top"] = '|'.join(toks)
    except Exception:
        pass
    return sig
```

---

# 6) `page_change` 逻辑加固（避免同帧比同帧失误）

在 `act_wait_for()` 的规则解析里，`page_change` 的实现现状是拿同一帧比同一帧；改为**与进入 wait 前的快照对比**：

在进入 `act_wait_for` 时先捕获基准签名：

```python
def act_wait_for(self, until: Dict[str, Any]) -> bool:
    # ...
    # 基准签名用于 page_change 对比
    try:
        base_sig = self._signature(self.ctx.get("last_bgr"), self.ctx.get("detections"))
    except Exception:
        base_sig = None
    # ...
    while time.time() < deadline:
        self._grab()
        self._detect()
        # ...
        if isinstance(r, str) and r == "page_change":
            # 与进入 wait 时的 base_sig 比较
            sig2 = self._signature(self.ctx["last_bgr"], dets)
            if base_sig is not None and self._sig_sim(base_sig, sig2) < _env_float("WF_PAGECHANGE_SIM_THR", 0.72):
                return True
```

---

# 7) `act_open_url` 默认浏览器可配（vars/env）

```python
def act_open_url(self, url: str, app: Optional[str] = "Google Chrome") -> None:
    # 优先 workflow.vars.default_browser → env DEFAULT_BROWSER → 参数
    app2 = _wf_var(self, "default_browser") or os.getenv("DEFAULT_BROWSER") or app or "Google Chrome"
    sysname = platform.system()
    try:
        if sysname == "Darwin" and app2:
            subprocess.run(["open", "-a", app2, url], check=False)
            return
        if sysname == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    webbrowser.open(url)
```

---

# 8) `os.activate_app` / `os.launch_app` 支持多别名 `names`

在 `run_actions` 的两个分支中，加入 `names` 的通用处理（兼容旧的 `name`）：

```python
elif op == "os.activate_app":
    names = act.get("names")
    if not names:
        # vars.os_app_names 优先；否则单个 name；否则 env OS_APP_NAMES（逗号分隔）
        names = _wf_list(self, "os_app_names") or ([act.get("name")] if act.get("name") else None) or _env_list("OS_APP_NAMES", ["WeChat","微信"])
    ok = False
    for name in names or []:
        try:
            if platform.system() == "Darwin":
                subprocess.run(["osascript", "-e", f'tell application "{name}" to activate'], check=True)
                ok = True
                break
            elif platform.system() == "Windows":
                ps = rf'''
                $ErrorActionPreference = 'SilentlyContinue'
                $p = Get-Process -Name "{name}" | Select-Object -First 1
                if ($p -and $p.MainWindowHandle -ne 0) {{
                  $sig = '[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr hWnd);'
                  Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Win32 | Out-Null
                  [Win32.WinAPI]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
                  Write-Output 'OK'
                }} else {{
                  Write-Output 'NOHWND'
                }}
                '''
                out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], stderr=subprocess.DEVNULL, timeout=5)
                s = (out or b"").decode("utf-8", errors="ignore").strip()
                if s.startswith("OK"):
                    ok = True; break
        except Exception:
            pass
    sv = act.get("save")
    if isinstance(sv, str) and sv:
        self.ctx[sv] = bool(ok)
    if not ok and not bool(act.get("soft")):
        raise RuntimeError(f"os.activate_app failed for names={names}")

elif op == "os.launch_app":
    names = act.get("names")
    if not names:
        names = _wf_list(self, "os_app_names") or ([act.get("name")] if act.get("name") else None) or _env_list("OS_APP_NAMES", ["WeChat","微信"])
    path = act.get("path")
    ok = False
    try:
        if platform.system() == "Darwin":
            if path: subprocess.run(["open", path], check=True); ok = True
            else:
                for name in names or []:
                    try:
                        subprocess.run(["open", "-a", name], check=True); ok = True; break
                    except Exception:
                        continue
        elif platform.system() == "Windows":
            if path:
                subprocess.run(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath '{path}'"], check=True); ok = True
            else:
                for name in names or []:
                    try:
                        subprocess.run(["powershell", "-NoProfile", "-Command", f"Start-Process '{name}'"], check=True); ok = True; break
                    except Exception:
                        continue
    except Exception:
        ok = False
    sv = act.get("save")
    if isinstance(sv, str) and sv:
        self.ctx[sv] = bool(ok)
    if not ok and not bool(act.get("soft")):
        raise RuntimeError(f"os.launch_app failed for names={names} path={path or ''}")
```

---

# 9) graph 保存加时间戳（可选）

```python
def _save_graph_workflow(self, start_id: Optional[str] = None) -> str:
    wf = {"start": start_id or (next(iter(self.graph["nodes"])) if self.graph["nodes"] else "open_home"),
          "states": {nid: {"actions": [{"do": "autostep"}], "on_success": "autonext"} for nid in self.graph["nodes"]}}
    ts = int(time.time()*1000)
    path = os.path.join("flows", f"auto_workflow_{ts}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    return path
```

---

# 10) 示例：`workflow.vars` 一次性集中配置

```json
"vars": {
  "capture": { "mode": "active_window" },
  "default_browser": "Google Chrome",
  "os_app_names": ["WeChat", "微信"],

  "danger_words": ["publish","delete","pay","submit","确认","发布","删除","支付","提交"],
  "loading_words": ["加载", "loading", "处理中", "正在", "刷新"],
  "toast_words": ["成功","已发布","完成","保存","已复制","success","saved","done"],

  "prefer_human_input": true, 
  "human_mouse": { "speed_px_per_s": 1200, "steps": 34, "overshoot_px": 6, "jitter_px": 2 },
  "human_type_interval_ms": 60
}
```

---

# 11) 环境变量清单（按需覆盖）

```
# 签名
WF_SIG_W_TILES=0.4
WF_SIG_W_YOLO=0.4
WF_SIG_W_LAYOUT=0.2
WF_SIG_TILE_COUNT=4
WF_SIG_LAYOUT_GRID=16
WF_SIG_OCR_TOPK=8
WF_PAGECHANGE_SIM_THR=0.72

# OCR token 长度
OCR_TOKEN_MIN_LEN=2
OCR_TOKEN_MAX_LEN=12

# 危险词/提示词
DANGER_DOUBLE_CONFIRM=1
DANGER_WORDS=publish,delete,pay,submit,确认,发布,删除,支付,提交
WF_LOADING_WORDS=加载,loading,处理中,正在,刷新
WF_TOAST_WORDS=成功,已发布,完成,保存,已复制,success,saved,done

# 浏览器与 App 名称
DEFAULT_BROWSER=Google Chrome
OS_APP_NAMES=WeChat,微信
```

---

# 12) 关于 patch 失败/对齐问题

* 建议逐段粘贴到对应函数内部，避免大块 diff 因空白行/缩进差异失败；
* `_sig_sim`、`_signature`、`_ocr_tokens_current`、`_detect_loading_toast`、`act_click`、`act_wait_for`、`act_open_url`、`os.activate_app`、`os.launch_app` 都是**局部替换**；
* 若你使用 `git apply`，可以把这份改动拆成若干小 diff，每次两三个函数，出错更容易定位。

