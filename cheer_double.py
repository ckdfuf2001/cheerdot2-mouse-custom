"""M-key click -> action (overlay).
Verified facts (log reverse-engineering):
- M button always sends key 0x51 / status 0 over BLE, one identical packet per
  click. NO hold/release info: a 3s hold produced no extra packet.
- PodMouse routes 0x51 to the pointer-style cycle; mKeyShort/Long never fire.
- With mKey_functions="-1" (single style) the cycle is a no-op (invisible).
- This tool tails PodMouse's debug log for press lines and fires the
  configured action on EVERY press, immediately.
- Action types: 키조합 (SendInput) / CMD 명령 (hidden cmd) / 프로그램 실행.
Needs: PodMouse running + LogLevel=debug (default).
Rollback button restores mKey_functions="-1,4,2" via official bridge.
"""
import json, os, re, sys, time, threading, ctypes
from ctypes import wintypes
from datetime import datetime

APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Cheerdots", "CheerCustom")
CFG = os.path.join(APP_DIR, "double_mapping.json")
LOG = os.path.join(os.environ.get("APPDATA", ""), "podmouse", "logs", "debug.txt")
ROLLBACK_FUNCS = "-1,4,2"

ACTION_TYPES = ["단일키", "키조합", "CMD 명령", "프로그램 실행", "PodMouse 기능"]
SPECIAL_KEYS = ["win", "ctrl", "alt", "shift", "esc", "enter", "tab", "space",
                "backspace", "delete", "insert", "home", "end",
                "pageup", "pagedown", "left", "up", "right", "down",
                "f1", "f2", "f3", "f4", "f5", "f6",
                "f7", "f8", "f9", "f10", "f11", "f12"]
ACTION_TYPES_ALL = list(ACTION_TYPES)

# PodMouse M-key function codes (from cheer_physical FUNCS / CustomKeyFunction.js)
# that we can execute locally at OS level. AI/voice/translation/webpage/file
# ones need PodMouse engines or extra input -> use 키조합/프로그램 실행 instead.
PODMOUSE_FUNCS = {
    11: ("Enter", {"type": "키조합", "value": "enter"}),
    12: ("뒤로", {"type": "키조합", "value": "alt+left"}),
    14: ("바탕화면 보기", {"type": "키조합", "value": "win+d"}),
    18: ("창 전환", {"type": "키조합", "value": "alt+tab"}),
    24: ("화면 잠금", {"type": "CMD 명령", "value": "rundll32.exe user32.dll,LockWorkStation"}),
    25: ("프로그램 닫기", {"type": "키조합", "value": "alt+f4"}),
    26: ("내 컴퓨터", {"type": "CMD 명령", "value": "explorer shell:MyComputerFolder"}),
    27: ("계산기", {"type": "프로그램 실행", "value": "calc.exe"}),
    28: ("작업 관리자", {"type": "키조합", "value": "ctrl+shift+esc"}),
    29: ("제어판", {"type": "CMD 명령", "value": "control"}),
    30: ("프로그램 제거", {"type": "CMD 명령", "value": "control appwiz.cpl"}),
    31: ("명령 프롬프트", {"type": "프로그램 실행", "value": "cmd.exe"}),
}
FUNC_OPTS = [f"{c} - {lbl}" for c, (lbl, _) in sorted(PODMOUSE_FUNCS.items())]

DEFAULT_CFG = {"action": {"type": "키조합", "value": "win"}, "enabled": True}

VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "control": 0x11, "meta": 0x5B,
      "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
      "backspace": 0x08, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
      "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22}
for i in range(1, 25):
    VK[f"f{i}"] = 0x6F + i
for c in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[c] = ord(c.upper())

PUL = ctypes.POINTER(ctypes.c_ulong)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", PUL)]
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", PUL)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]
class Input_I(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KeyBdInput), ("hi", HARDWAREINPUT)]
    _anonymous_ = ("u",); _fields_ = [("type", wintypes.DWORD), ("u", _U)]
assert ctypes.sizeof(Input_I) == 40, ctypes.sizeof(Input_I)
SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input_I), ctypes.c_int]
SendInput.restype = wintypes.UINT
KEYEVENTF_KEYUP = 0x0002

DBGLOG = os.path.join(APP_DIR, "double_debug.log")

def dbg(msg):
    try:
        with open(DBGLOG, "a", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%H:%M:%S.%f")[:-3] + " " + msg + "\n")
    except Exception:
        pass

def parse_keys(spec):
    parts = [p.strip().lower() for p in spec.replace("+", " ").split() if p.strip()]
    if not parts:
        raise ValueError("empty")
    vks = []
    for p in parts:
        if p not in VK:
            raise ValueError(f"unknown key: {p}")
        vks.append(VK[p])
    return vks

def send_keys(spec):
    res = []
    vks = parse_keys(spec)
    for vk in vks:
        ii = Input_I(); ii.type = 1; ii.ki.wVk = vk
        res.append(SendInput(1, ctypes.byref(ii), ctypes.sizeof(ii)))
    for vk in reversed(vks):
        ii = Input_I(); ii.type = 1; ii.ki.wVk = vk; ii.ki.dwFlags = KEYEVENTF_KEYUP
        res.append(SendInput(1, ctypes.byref(ii), ctypes.sizeof(ii)))
    return res

def do_action(action):
    """action = {"type":..., "value":...}. Returns text for log/status."""
    atype = action.get("type", "키조합")
    if atype == "키입력":
        atype = "키조합"
    if atype in SPECIAL_KEYS:
        # old shape: special key stored as the type
        return do_action({"type": "키조합", "value": atype})
    value = (action.get("value", "") or "").strip()
    if atype == "단일키":
        if value not in SPECIAL_KEYS and value.lower() not in SPECIAL_KEYS:
            raise ValueError(f"unknown key: {value}")
        return do_action({"type": "키조합", "value": value.lower()})
    value = (action.get("value", "") or "").strip()
    if atype == "PodMouse 기능":
        try:
            code = int(str(value).split("-")[0].strip())
        except Exception:
            raise ValueError(f"unknown function: {value}")
        if code not in PODMOUSE_FUNCS:
            raise ValueError(f"unsupported function: {code}")
        lbl, mapped = PODMOUSE_FUNCS[code]
        r = do_action(mapped)
        return f"podfunc {code}({lbl}) -> {r}"
    if not value:
        raise ValueError("empty")
    if atype == "키조합":
        r = send_keys(value)
        return f"key {value} -> {r}"
    elif atype == "CMD 명령":
        import subprocess
        subprocess.Popen(["cmd", "/c", value], creationflags=0x08000000,
                         close_fds=True)
        return f"cmd {value}"
    elif atype == "프로그램 실행":
        os.startfile(value)
        return f"run {value}"
    else:
        raise ValueError(f"unknown type: {atype}")

def load_cfg():
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(CFG):
        save_cfg(DEFAULT_CFG)
        return json.loads(json.dumps(DEFAULT_CFG))
    with open(CFG, encoding="utf-8") as f:
        d = json.load(f)
    # migrate old shapes -> single "action"
    if "action" not in d or not isinstance(d["action"], dict):
        src = None
        for k in ("tap1", "tap2", "single_keys", "tap2_keys", "keys",
                  "double_keys", "tap4_keys", "tap4"):
            if k in d:
                v = d.pop(k)
                src = v if isinstance(v, dict) else {"type": "키조합", "value": str(v)}
                break
        d["action"] = src if isinstance(src, dict) else dict(DEFAULT_CFG["action"])
    a = d["action"]
    if a.get("type") == "키입력":
        a["type"] = "키조합"
    if a.get("type") in SPECIAL_KEYS:
        a = {"type": "단일키", "value": a["type"]}
        d["action"] = a
    if a.get("type") == "키조합" and (a.get("value", "") or "").lower() in SPECIAL_KEYS \
            and "+" not in (a.get("value", "") or ""):
        a = {"type": "단일키", "value": a["value"].lower()}
        d["action"] = a
    a.setdefault("type", "키조합")
    a.setdefault("value", "")
    d.setdefault("enabled", True)
    return d

def save_cfg(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

TS_RE = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{3})')
KEY_RE = re.compile(r'key : 0x51\b')

def line_ts(line):
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        base = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
        return base.timestamp() + int(m.group(2)) / 1000.0
    except Exception:
        return None

def bridge_set_functions(value):
    import urllib.request, asyncio
    pages = json.load(urllib.request.urlopen('http://127.0.0.1:9000/json/list', timeout=8))
    cands = [p for p in pages if 'SplitMouse' in (p.get('title') or '')
             or 'detached_mouse' in (p.get('url') or '') or 'device_2_0' in (p.get('url') or '')]
    if not cands:
        raise RuntimeError('PodMouse page not found (is PodMouse running?)')
    ws_url = cands[0]['webSocketDebuggerUrl']
    req = f"device/mouse/setFunctions?functions={value}"

    async def go():
        import websockets
        async with websockets.connect(ws_url, max_size=8_000_000) as ws:
            js = ("new Promise((resolve)=>{"
                  "window.CefViewQuery({request:" + json.dumps(req) + ",persistent:false,"
                  "onSuccess:(r)=>resolve('OK:'+String(r).slice(0,200)),"
                  "onFailure:(c,m)=>resolve('FAIL:'+c+':'+String(m).slice(0,200))});})")
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                                      'params': {'expression': js, 'awaitPromise': True, 'returnByValue': True}}))
            async for msg in ws:
                d = json.loads(msg)
                if d.get('id') == 1:
                    return d['result']['result']['value']
    return asyncio.run(go())

MOD_KEYS = {"Control_L": "ctrl", "Control_R": "ctrl", "Alt_L": "alt", "Alt_R": "alt",
            "Shift_L": "shift", "Shift_R": "shift", "Win_L": "win", "Win_R": "win",
            "Meta_L": "win", "Meta_R": "win"}
MAIN_MAP = {"Return": "enter", "Tab": "tab", "Escape": "esc", "space": "space",
            "BackSpace": "backspace", "Prior": "pageup", "Next": "pagedown",
            "Left": "left", "Right": "right", "Up": "up", "Down": "down",
            "Insert": "insert", "Delete": "delete", "Home": "home", "End": "end"}

class CaptureEntry:
    """Click -> captures physical keys (like a hotkey field).
    Empty/unfinished -> reverts to original value."""
    def __init__(self, master, var, width=20):
        from tkinter import ttk
        self.var = var
        self.box = ttk.Entry(master, textvariable=var, state="readonly", width=width)
        self.committed = var.get()
        self.mods = []
        self.box.bind("<KeyPress>", self.on_press)
        self.box.bind("<FocusIn>", self.on_focus)
        self.box.bind("<FocusOut>", self.on_blur)

    def grid(self, **kw):
        self.box.grid(**kw)

    def grid_remove(self):
        self.box.grid_remove()

    def revert(self):
        self.var.set(self.committed)
        self.mods = []

    def on_focus(self, e):
        self.committed = self.var.get()
        self.mods = []

    def on_blur(self, e):
        if self.var.get().endswith("+...") or self.var.get() == "":
            self.revert()
        else:
            self.committed = self.var.get()
        self.mods = []

    def on_press(self, e):
        ks = e.keysym
        if ks in MOD_KEYS:
            m = MOD_KEYS[ks]
            if m not in self.mods:
                self.mods.append(m)
            self.var.set("+".join(self.mods) + "+...")
            return "break"
        if ks == "Escape" and not self.mods:
            self.revert()
            self.box.master.focus_set()
            return "break"
        if ks == "BackSpace" and not self.mods:
            self.revert()
            return "break"
        if ks in MAIN_MAP:
            main = MAIN_MAP[ks]
        elif len(ks) == 1:
            main = ks.lower()
        elif (ks.startswith("F") or ks.startswith("f")) and ks[1:].isdigit():
            main = ks.lower()
        else:
            return "break"
        self.var.set("+".join(self.mods + [main]))
        self.committed = self.var.get()
        self.mods = []
        return "break"

class Watcher(threading.Thread):
    daemon = True
    def __init__(self, on_press, on_fire):
        super().__init__()
        self.on_press = on_press
        self.on_fire = on_fire  # (kind, text)
        self._stop = threading.Event()

    def _fire(self):
        cfg = load_cfg()
        if not cfg.get("enabled", True):
            dbg("suppressed (watch disabled)")
            return
        try:
            r = do_action(cfg.get("action", {}))
            dbg(f"fire {r}")
        except Exception as e:
            dbg(f"fire FAIL {e!r}")
            r = f"실패: {e}"
        self.on_fire("2번클릭", r)

    def run(self):
        try:
            pos = os.path.getsize(LOG) if os.path.exists(LOG) else 0
        except Exception:
            pos = 0
        dbg("watcher started")
        while not self._stop.is_set():
            try:
                if not os.path.exists(LOG):
                    time.sleep(0.5); continue
                size = os.path.getsize(LOG)
                if size < pos:
                    pos = 0
                if size > pos:
                    with open(LOG, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(pos)
                        chunk = f.read()
                    pos = size
                    for line in chunk.splitlines():
                        if KEY_RE.search(line):
                            ts = line_ts(line) or time.time()
                            dbg(f"press ts={ts:.3f}")
                            self.on_press(ts)
                            threading.Thread(target=self._fire, daemon=True).start()
                else:
                    time.sleep(0.15)
            except Exception as e:
                dbg(f"watcher ERR {e!r}")
                time.sleep(0.5)

SUPPRESS_FUNCS = "-1"  # single style = cycle no-op (original action suppressed)

def enforce_suppress():
    """Force mKey_functions to SUPPRESS_FUNCS via official bridge.
    Returns (ok, text)."""
    import urllib.request, asyncio
    pages = json.load(urllib.request.urlopen('http://127.0.0.1:9000/json/list', timeout=8))
    cands = [p for p in pages if 'SplitMouse' in (p.get('title') or '')
             or 'detached_mouse' in (p.get('url') or '') or 'device_2_0' in (p.get('url') or '')]
    if not cands:
        raise RuntimeError('PodMouse page not found')
    ws_url = cands[0]['webSocketDebuggerUrl']
    req = f"device/mouse/setFunctions?functions={SUPPRESS_FUNCS}"

    async def go():
        import websockets
        async with websockets.connect(ws_url, max_size=8_000_000) as ws:
            js = ("new Promise((resolve)=>{"
                  "window.CefViewQuery({request:" + json.dumps(req) + ",persistent:false,"
                  "onSuccess:(r)=>resolve('OK'),"
                  "onFailure:(c,m)=>resolve('FAIL:'+c+':'+m)});})")
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                                      'params': {'expression': js, 'awaitPromise': True, 'returnByValue': True}}))
            async for msg in ws:
                d = json.loads(msg)
                if d.get('id') == 1:
                    return d['result']['result']['value']
    return asyncio.run(go())

def live_functions():
    """Read mKey_functions from PodMouse's settings JSON file (it saves on change)."""
    import glob as _glob
    files = sorted(_glob.glob(os.path.join(os.environ.get("APPDATA", ""), "podmouse",
                                           "config", "setting", "bluetooth-*.json")))
    if not files:
        return None
    try:
        return json.load(open(files[0], encoding="utf-8")).get("mKey_functions")
    except Exception:
        return None

class SuppressWatch(threading.Thread):
    """While our watch is enabled, keep original action suppressed.
    (PodMouse/device sometimes reports styles back and reverts.)"""
    daemon = True
    def __init__(self, on_note):
        super().__init__()
        self.on_note = on_note
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                if load_cfg().get("enabled", True):
                    cur = live_functions()
                    if cur is not None and cur != SUPPRESS_FUNCS:
                        try:
                            enforce_suppress()
                            dbg(f"watchdog: functions {cur!r} -> {SUPPRESS_FUNCS!r}")
                            self.on_note(f"원래기능 억제 유지 ({cur}→{SUPPRESS_FUNCS})")
                        except Exception as e:
                            dbg(f"watchdog FAIL {e!r}")
            except Exception as e:
                dbg(f"watchdog ERR {e!r}")
            self._stop.wait(20)

def main():
    import tkinter as tk
    from tkinter import ttk, messagebox
    cfg = load_cfg()
    presses, fired = [0], [0]

    root = tk.Tk()
    root.title("M 클릭 → 액션")
    ttk.Label(root, text="M 누를 때마다 아래 동작 실행.\n전제: PodMouse 실행 + 스타일 단일화(-1).",
              foreground="gray").pack(padx=10, pady=6)

    a = cfg.get("action", {"type": "키조합", "value": "win"})
    if a.get("type") in SPECIAL_KEYS:  # old shape: special stored as type
        a = {"type": "단일키", "value": a["type"]}
    a_type = tk.StringVar(value=a.get("type", "키조합"))
    a_var = tk.StringVar(value=a.get("value", "win"))
    st = tk.StringVar(value="대기 중")

    fr = ttk.Frame(root); fr.pack(pady=4)
    ttk.Label(fr, text="2번클릭:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
    cb = ttk.Combobox(fr, textvariable=a_type, values=ACTION_TYPES_ALL, width=11, state="readonly")
    cb.grid(row=0, column=1, padx=4, pady=2)
    cap = CaptureEntry(fr, a_var)
    cap.grid(row=0, column=2, padx=4, pady=2)
    txt = ttk.Entry(fr, textvariable=a_var, width=22)
    lbl = ttk.Label(fr, text="", width=22)
    spec_var = tk.StringVar(value="")
    spec_cb = ttk.Combobox(fr, textvariable=spec_var, values=SPECIAL_KEYS, width=22,
                           state="readonly")
    func_var = tk.StringVar(value="")
    func_cb = ttk.Combobox(fr, textvariable=func_var, values=FUNC_OPTS, width=22,
                           state="readonly")
    def on_browse():
        from tkinter import filedialog
        p = filedialog.askopenfilename(
            title="실행할 프로그램 선택",
            filetypes=[("실행 파일", "*.exe *.bat *.cmd *.msi *.lnk"),
                       ("모든 파일", "*.*")])
        if p:
            a_var.set(p)
    btn_find = ttk.Button(fr, text="찾기...", command=on_browse, width=7)

    def func_code():
        try:
            return int(str(func_var.get()).split("-")[0].strip())
        except Exception:
            return None

    def sync_entries(*args):
        # 키조합=캡처박스, CMD=텍스트박스, 프로그램=텍스트+찾기,
        # PodMouse 기능=기능 드롭다운, 단일키=특수키 드롭다운
        for w in (cap.box, txt, spec_cb, btn_find, func_cb):
            w.grid_remove()
        t = a_type.get()
        if t == "키조합":
            cap.grid(row=0, column=2, padx=4, pady=2)
        elif t == "CMD 명령":
            txt.grid(row=0, column=2, padx=4, pady=2)
        elif t == "프로그램 실행":
            txt.grid(row=0, column=2, padx=4, pady=2)
            btn_find.grid(row=0, column=3, padx=4, pady=2)
        elif t == "PodMouse 기능":
            code = None
            try:
                code = int(str(a_var.get()).split("-")[0].strip())
            except Exception:
                code = None
            if code in PODMOUSE_FUNCS:
                func_var.set(f"{code} - {PODMOUSE_FUNCS[code][0]}")
            elif not func_var.get():
                func_var.set(FUNC_OPTS[0])
            func_cb.grid(row=0, column=2, padx=4, pady=2)
        elif t == "단일키":
            v = (a_var.get() or "").strip().lower()
            spec_var.set(v if v in SPECIAL_KEYS else "win")
            spec_cb.grid(row=0, column=2, padx=4, pady=2)
        else:
            lbl.config(text=f"단독키: {t}")
            lbl.grid(row=0, column=2, padx=4, pady=2)
    a_type.trace_add("write", sync_entries)
    func_var.trace_add("write", lambda *a: a_var.set(str(func_code() or "")))
    spec_var.trace_add("write", lambda *a: a_var.set(spec_var.get()))
    sync_entries()
    ttk.Label(root, text="(키조합: 입력창 클릭 후 키 직접 입력. PodMouse 기능: 번호 선택. CMD: 명령어(예: notepad), 프로그램: 경로·URL)",
              foreground="gray").pack(padx=10, pady=2)
    def refresh_status(msg=None):
        en = "켬" if load_cfg().get("enabled", True) else "꺼짐"
        st.set(((msg + " | ") if msg else "") +
               f"눌림 {presses[0]} · 실행 {fired[0]} · 감시 {en}")
    ttk.Label(root, textvariable=st, foreground="green").pack(pady=4)

    def on_press(ts):
        presses[0] += 1
        root.after(0, refresh_status)
    def on_fire(kind, text):
        fired[0] += 1
        root.after(0, lambda: refresh_status(f"{kind}: {text}"))
    Watcher(on_press, on_fire).start()
    SuppressWatch(lambda m: root.after(0, lambda: refresh_status(m))).start()

    bf = ttk.Frame(root); bf.pack(pady=6)
    def current_action():
        t = a_type.get()
        if t in SPECIAL_KEYS:
            return {"type": "단일키", "value": t}
        if t == "단일키":
            v = spec_var.get().strip().lower()
            if v not in SPECIAL_KEYS:
                raise ValueError(f"unknown key: {v}")
            return {"type": "단일키", "value": v}
        if t == "PodMouse 기능":
            code = func_code()
            if code not in PODMOUSE_FUNCS:
                raise ValueError(f"unknown function: {func_var.get()}")
            return {"type": "PodMouse 기능", "value": str(code)}
        v = a_var.get().strip()
        if not v or v.endswith("..."):
            old = cfg.get("action", {"type": "키조합", "value": "win"})
            a_type.set(old.get("type", "키조합"))
            if old.get("type") not in SPECIAL_KEYS and old.get("type") != "PodMouse 기능":
                a_var.set(old.get("value", ""))
            return dict(old)
        a = {"type": t, "value": v}
        if a["type"] == "키조합":
            parse_keys(a["value"])
        return a
    def on_apply():
        try:
            a = current_action()
            cfg["action"] = a
            cfg["enabled"] = True
            save_cfg(cfg)
            try:
                enforce_suppress()
                note = " + 원래기능 억제(-1)"
            except Exception as e:
                note = f" (억제 실패: {e} - 수동 확인 필요)"
                dbg(f"apply suppress FAIL {e!r}")
            refresh_status(f"저장됨: [{a['type']}] {a['value']} (감시 켬){note}")
        except ValueError as e:
            messagebox.showerror("오류", f"키 형식 오류: {e}\n예: ctrl+a, alt+f4, F5, win")
        except Exception as e:
            messagebox.showerror("오류", str(e))
    def on_test():
        try:
            r = do_action(current_action())
            refresh_status(f"테스트: {r}")
        except Exception as e:
            messagebox.showerror("오류", str(e))
    def on_rollback():
        if messagebox.askyesno("원복", "스타일 순환을 원래대로(-1,4,2) 되돌리고 감시를 끌까요?"):
            try:
                res = bridge_set_functions(ROLLBACK_FUNCS)
                cfg["enabled"] = False
                save_cfg(cfg)
                refresh_status("원복됨 (감시 꺼짐): " + res[:40])
            except Exception as e:
                messagebox.showerror("연결 실패", f"{e}\nPodMouse가 실행 중인지 확인하세요.")
    ttk.Button(bf, text="적용", command=on_apply).pack(side="left", padx=3)
    ttk.Button(bf, text="테스트", command=on_test).pack(side="left", padx=3)
    ttk.Button(bf, text="원복(-1,4,2)", command=on_rollback).pack(side="left", padx=3)
    refresh_status("실행 중")
    root.protocol("WM_DELETE_WINDOW", root.withdraw)
    root.mainloop()

if __name__ == "__main__":
    # single instance guard (avoid double-firing from duplicates)
    _lock = os.path.join(APP_DIR, "cheer_double.lock")
    try:
        if os.path.exists(_lock):
            _old = int(open(_lock, encoding="utf-8").read().strip() or "0")
            os.kill(_old, 0)  # raises if dead
            sys.exit(0)  # another live instance -> quit quietly
    except Exception:
        pass
    try:
        open(_lock, "w", encoding="utf-8").write(str(os.getpid()))
    except Exception:
        pass
    main()
