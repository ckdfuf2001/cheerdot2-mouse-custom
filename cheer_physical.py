"""CheerDots2 PHYSICAL key mapper (official path, no overlay).
Calls PodMouse's own save API through its CEF bridge (CefViewQuery),
same as the built-in Mkey page: device/setDeviceSetting?field=value.
This saves to per-device JSON AND pushes to the device over BLE/HID.
JSON-direct edit alone does NOT reach the device (verified via logs).
Needs PodMouse running (CEF remote debugging on 127.0.0.1:9000).
Fields: mKeyShort_function (short), mKeyLong_function (long),
  function 15 = custom shortcut -> mKey_shortcut_Str/key/modifiers.
Double-click = firmware-fixed pointer-shape cycle (not mappable).
"""
import json, os, sys, glob, shutil, subprocess, datetime
import tkinter as tk
from tkinter import ttk, messagebox

SETTING_DIR = os.path.join(os.environ.get("APPDATA", ""), "podmouse", "config", "setting")
PODMOUSE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Cheerdots", "PodMouse.exe")

FUNCS = [
    (-1, "미지정"),
    (7, "음성 입력"),
    (8, "번역 입력"),
    (9, "스크린샷 번역"),
    (11, "Enter"),
    (12, "뒤로"),
    (14, "바탕화면 보기"),
    (15, "커스텀 단축키 (아래 입력창)"),
    (16, "음성 검색"),
    (18, "창 전환 (Alt+Tab)"),
    (19, "웹페이지 열기"),
    (21, "AI 열기"),
    (22, "회의 모드"),
    (23, "음성입력 전송"),
    (24, "화면 잠금"),
    (25, "프로그램 닫기"),
    (26, "내 컴퓨터"),
    (27, "계산기"),
    (28, "작업 관리자"),
    (29, "제어판"),
    (30, "프로그램 제거"),
    (31, "명령 프롬프트"),
    (32, "프로그램 열기"),
    (33, "파일 열기"),
    (1007, "받아쓰기 모드"),
]
LABEL = {v: l for v, l in FUNCS}

QT_MOD = {"ctrl": 0x04000000, "alt": 0x08000000, "shift": 0x02000000, "win": 0x10000000,
          "control": 0x04000000, "meta": 0x10000000}
QT_F = {f"F{i}": 0x01000030 + (i - 1) for i in range(1, 36)}
QT_SPECIAL = {"enter": 0x01000004, "return": 0x01000004, "tab": 0x01000009, "esc": 0x01000000,
              "escape": 0x01000000, "space": 0x20, "backspace": 0x01000003,
              "left": 0x01000012, "up": 0x01000013, "right": 0x01000014, "down": 0x01000015,
              "insert": 0x01000006, "delete": 0x01000007, "home": 0x01000010, "end": 0x01000011,
              "pageup": 0x01000016, "pagedown": 0x01000017}

def parse_shortcut(spec):
    """'Ctrl+Shift+C' -> (QtKey int, QtModifiers int, pretty Str). Raises ValueError."""
    parts = [p.strip().lower() for p in spec.replace("+", " ").split() if p.strip()]
    if not parts:
        raise ValueError("empty")
    mods, keys = 0, []
    for p in parts:
        if p in QT_MOD:
            mods |= QT_MOD[p]
        elif p in QT_F:
            keys.append(QT_F[p])
        elif p in QT_SPECIAL:
            keys.append(QT_SPECIAL[p])
        elif len(p) == 1:
            keys.append(ord(p.upper()))
        else:
            raise ValueError(f"unknown key: {p}")
    if len(keys) != 1:
        raise ValueError("main key must be exactly one (e.g. Ctrl+C)")
    return keys[0], mods

def find_setting_files():
    return sorted(glob.glob(os.path.join(SETTING_DIR, "bluetooth-*.json")))

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cdp_bridge_call(request, timeout_s=15):
    """Call PodMouse's CefViewQuery bridge via CEF remote debugging (127.0.0.1:9000).
    Returns (ok, text). Raises on connection problems."""
    import urllib.request
    import asyncio
    pages = json.load(urllib.request.urlopen('http://127.0.0.1:9000/json/list', timeout=8))
    cands = [p for p in pages if 'SplitMouse' in (p.get('title') or '')
             or 'detached_mouse' in (p.get('url') or '') or 'device_2_0' in (p.get('url') or '')]
    if not cands:
        raise RuntimeError('PodMouse 설정 페이지(SplitMouse)를 못 찾음. PodMouse 실행 확인.')
    ws_url = cands[0]['webSocketDebuggerUrl']

    async def go():
        import websockets
        async with websockets.connect(ws_url, max_size=8_000_000) as ws:
            js = ("new Promise((resolve)=>{"
                  "try{"
                  "if(typeof window.CefViewQuery==='undefined'){resolve('NOBRIDGE');return;}"
                  "window.CefViewQuery({request:" + json.dumps(request) + ",persistent:false,"
                  "onSuccess:(r)=>resolve('OK:'+String(r).slice(0,400)),"
                  "onFailure:(c,m)=>resolve('FAIL:'+c+':'+String(m).slice(0,200))});"
                  "}catch(e){resolve('EX:'+e);}})")
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                                      'params': {'expression': js, 'awaitPromise': True, 'returnByValue': True}}))
            async for msg in ws:
                d = json.loads(msg)
                if d.get('id') == 1:
                    return d['result']['result']['value']
    return True, asyncio.run(asyncio.wait_for(go(), timeout_s))

def stop_podmouse():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "PodMouse.exe"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    import time
    time.sleep(2)  # 종료 시 파일 쓰기 끝날 때까지 대기 (덮어쓰기 방지)

def start_podmouse(status_cb):
    try:
        subprocess.Popen([PODMOUSE], close_fds=True)
        status_cb("PodMouse 재시작됨 - 장치에 적용 중 (HID)")
    except Exception as e:
        status_cb(f"PodMouse 실행 실패: {e} (수동 실행: {PODMOUSE})")

def restart_podmouse(status_cb):
    stop_podmouse()
    start_podmouse(status_cb)

def main():
    files = find_setting_files()
    if not files:
        messagebox.showerror("오류", f"장치 설정 파일이 없음:\n{SETTING_DIR}\nPodMouse를 한번 실행해 페어링부터 하세요.")
        sys.exit(1)
    path = files[0]
    bak = path + ".orig-backup.json"
    if not os.path.exists(bak):
        shutil.copy(path, bak)
    data = load_json(path)

    rows = [
        {"field": "mKeyShort_function", "label": "M키 짧게 (클릭)"},
        {"field": "mKeyLong_function", "label": "M키 길게 (롱클릭)"},
    ]

    root = tk.Tk()
    root.title("CheerDots2 물리키 매퍼 (M키 짧게/길게 + 포인터 모양)")
    ttk.Label(root, text=f"설정 파일: {path}\n※ M키: 짧게/길게만 변경 가능. 두번 클릭=펌웨어 고정(포인터 모양 순환: 레이저→스포트라이트→디지털라이트)",
              foreground="gray").pack(padx=10, pady=6)

    vars_ = {}
    for r in rows:
        fr = ttk.LabelFrame(root, text=r["label"]); fr.pack(fill="x", padx=10, pady=5)
        cur = data.get(r["field"], -1)
        ttk.Label(fr, text=f"현재값(기본): {cur} ({LABEL.get(cur, '알 수 없음')})").pack(anchor="w", padx=6)
        cb = ttk.Combobox(fr, values=[f"{v} - {l}" for v, l in FUNCS], width=32, state="readonly")
        try:
            cb.current([v for v, _ in FUNCS].index(cur))
        except ValueError:
            cb.current(0)
        cb.pack(side="left", padx=6, pady=4)
        vars_[r["field"]] = cb

    fr2 = ttk.LabelFrame(root, text="커스텀 단축키 (기능=15 선택 시)"); fr2.pack(fill="x", padx=10, pady=5)
    ttk.Label(fr2, text="예: Ctrl+C, Ctrl+Shift+S, F5, Alt+F4").pack(anchor="w", padx=6)
    sc_var = tk.StringVar(value=data.get("mKey_shortcut_Str", "") or "")
    ttk.Entry(fr2, textvariable=sc_var, width=30).pack(side="left", padx=6, pady=4)
    ttk.Label(fr2, text="현재: " + (data.get("mKey_shortcut_Str", "") or "(없음)")).pack(side="left", padx=6)

    fr3 = ttk.LabelFrame(root, text="포인터 모양 (두번 클릭 시 순환되는 모양의 설정)"); fr3.pack(fill="x", padx=10, pady=5)
    ttk.Label(fr3, text="커서색 (#RRGGBB)").grid(row=0, column=0, padx=6, sticky="w")
    col_var = tk.StringVar(value=data.get("mKey_cursorColor", "#FF0000"))
    ttk.Entry(fr3, textvariable=col_var, width=10).grid(row=0, column=1, padx=6)
    ttk.Label(fr3, text="커서반경").grid(row=1, column=0, padx=6, sticky="w")
    rad_var = tk.StringVar(value=str(data.get("mKey_cursorRadius", 25)))
    ttk.Entry(fr3, textvariable=rad_var, width=10).grid(row=1, column=1, padx=6)
    ttk.Label(fr3, text="스포트라이트 반경").grid(row=2, column=0, padx=6, sticky="w")
    spot_var = tk.StringVar(value=str(data.get("mKey_spotLightRadius", 100)))
    ttk.Entry(fr3, textvariable=spot_var, width=10).grid(row=2, column=1, padx=6)
    ttk.Label(fr3, text=f"현재: {data.get('mKey_cursorColor','#FF0000')} / r={data.get('mKey_cursorRadius',25)} / spot={data.get('mKey_spotLightRadius',100)}").grid(row=3, column=0, columnspan=2, padx=6, sticky="w")

    st = tk.StringVar(value="대기 중")
    ttk.Label(root, textvariable=st, foreground="green").pack(pady=4)

    def stamp(msg):
        st.set(f"{msg} ({datetime.datetime.now().strftime('%H:%M:%S')})")

    def on_apply():
        try:
            shorts_sel = {r["field"]: int(vars_[r["field"]].get().split(" - ")[0]) for r in rows}
            sc_spec = sc_var.get().strip()
            col = col_var.get().strip() or "#FF0000"
            rad = int(rad_var.get().strip() or 25)
            spot = int(spot_var.get().strip() or 100)
            if any(v == 15 for v in shorts_sel.values()) and not sc_spec:
                messagebox.showwarning("안내", "기능 15(커스텀 단축키)를 골랐으면 단축키를 입력하세요.")
                return
            if any(v == 15 for v in shorts_sel.values()):
                key, mods = parse_shortcut(sc_spec)  # 형식 미리 검증
            # 공식 경로: 실행 중 PodMouse의 CefViewQuery로 저장 (JSON+장치 푸시)
            stamp("공식 경로로 적용 중...")
            root.update()
            calls = [(r["field"], shorts_sel[r["field"]]) for r in rows]
            calls += [("mKey_cursorColor", col), ("mKey_cursorRadius", rad),
                      ("mKey_spotLightRadius", spot)]
            if any(v == 15 for v in shorts_sel.values()):
                calls += [("mKey_shortcut_Str", sc_spec), ("mKey_shortcut_key", key),
                          ("mKey_shortcut_modifiers", mods)]
            results = []
            for field, val in calls:
                import urllib.parse
                req = f"device/setDeviceSetting?{field}={urllib.parse.quote(str(val))}"
                try:
                    _, res = cdp_bridge_call(req)
                except Exception as e:
                    messagebox.showerror("연결 실패",
                        f"PodMouse 브릿지 연결 실패: {e}\nPodMouse가 실행 중인지 확인하세요.")
                    return
                results.append(f"{field}={res[:60]}")
                if not res.startswith("OK:"):
                    messagebox.showwarning("일부 실패", "\n".join(results))
                    stamp("적용 중단됨 (위 메시지 확인)")
                    return
            save_note = " (JSON은 PodMouse가 직접 저장)"
            stamp(f"적용됨: 짧게={shorts_sel['mKeyShort_function']} 길게={shorts_sel['mKeyLong_function']}{save_note}")
            messagebox.showinfo("적용됨", "M키에 바로 눌러서 테스트하세요. 재시작 불필요.")
        except ValueError as e:
            messagebox.showerror("단축키 오류", f"단축키 형식 오류: {e}\n예: Ctrl+C")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    def on_rollback():
        if messagebox.askyesno("원복", f"백업으로 되돌릴까요?\n{bak}\n(오버레이 감시도 함께 꺼집니다)"):
            stop_podmouse()
            shutil.copy(bak, path)
            d2 = load_json(path)
            for r in rows:
                try:
                    vars_[r["field"]].current([v for v, _ in FUNCS].index(d2.get(r["field"], -1)))
                except ValueError:
                    vars_[r["field"]].current(0)
            sc_var.set(d2.get("mKey_shortcut_Str", "") or "")
            col_var.set(d2.get("mKey_cursorColor", "#FF0000"))
            rad_var.set(str(d2.get("mKey_cursorRadius", 25)))
            spot_var.set(str(d2.get("mKey_spotLightRadius", 100)))
            try:  # 오버레이 감시도 함께 끄기 (둘 다 도는 것 방지)
                import json as _json
                _cfg = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Cheerdots",
                                    "CheerCustom", "double_mapping.json")
                if os.path.exists(_cfg):
                    _d = _json.load(open(_cfg, encoding="utf-8"))
                    _d["enabled"] = False
                    _json.dump(_d, open(_cfg, "w", encoding="utf-8"),
                               ensure_ascii=False, indent=2)
            except Exception:
                pass
            stamp("원복됨 (백업 복구 + 감시 꺼짐)")
            restart_podmouse(stamp)

    bf = ttk.Frame(root); bf.pack(pady=6)
    ttk.Button(bf, text="적용(공식 경로, 재시작 불필요)", command=on_apply).pack(side="left", padx=4)
    ttk.Button(bf, text="원복", command=on_rollback).pack(side="left", padx=4)
    ttk.Label(root, text="적용=PodMouse 내장 저장 API 호출 → 장치에 즉시 푸시. PodMouse 실행 중이어야 함.",
              foreground="gray").pack(pady=4)
    root.mainloop()

if __name__ == "__main__":
    main()
