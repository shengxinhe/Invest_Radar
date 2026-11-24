# -*- coding: utf-8 -*-
"""截图工具：CDP 注入 cookie + 导航 + 截图（M4）"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time

import requests

U = "http://127.0.0.1:8000"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUT = r"C:\Users\32333\Desktop\project\money\out"


def shot(actions, out_name, w=430, h=932):
    """actions: [(kind, payload)] — navigate/click/wait/eval"""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    r = s.post(f"{U}/api/auth/login",
               json={"password": "tiger-tiger-amber-2318"}, timeout=30)
    assert r.json().get("ok")
    sid = s.cookies.get("radar_sid")

    prof = tempfile.mkdtemp()
    proc = subprocess.Popen([
        EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
        f"--user-data-dir={prof}", "--remote-debugging-port=9334",
        f"--window-size={w},{h}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    page = None
    for _ in range(20):
        try:
            t = requests.get("http://127.0.0.1:9334/json", timeout=2,
                             proxies={"http": None, "https": None}).json()
            ps = [x for x in t if x.get("type") == "page"]
            if ps:
                page = ps[0]
                break
        except Exception:
            pass
        time.sleep(0.5)
    assert page, "CDP not ready"

    from websocket import create_connection
    ws = create_connection(page["webSocketDebuggerUrl"], timeout=30)
    _id = [0]

    def send(method, params=None):
        _id[0] += 1
        ws.send(json.dumps({"id": _id[0], "method": method, "params": params or {}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == _id[0]:
                return m.get("result")

    send("Network.enable")
    send("Page.enable")
    send("Network.setCookie", {"name": "radar_sid", "value": sid,
                               "domain": "127.0.0.1", "path": "/",
                               "httpOnly": True, "sameSite": "Lax"})
    send("Emulation.setDeviceMetricsOverride",
         {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": True})
    send("Page.navigate", {"url": U + "/"})
    time.sleep(5)

    for kind, payload in actions:
        if kind == "wait":
            time.sleep(payload)
        elif kind == "eval":
            send("Runtime.evaluate", {"expression": payload, "awaitPromise": True})
            time.sleep(1)
        elif kind == "type":
            # 用真实坐标点击搜索框，触发 Vue @focus
            box = send("Runtime.evaluate", {
                "expression": """(() => {
                    const el = document.querySelector('.search-box input');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                })()""",
                "returnByValue": True})
            pt = (box.get("result") or {}).get("value")
            if pt:
                for ev in ("mousePressed", "mouseReleased"):
                    send("Input.dispatchMouseEvent", {
                        "type": ev, "x": pt["x"], "y": pt["y"],
                        "button": "left", "clickCount": 1})
                time.sleep(0.4)
            for ch in payload:
                send("Input.dispatchKeyEvent",
                     {"type": "keyDown", "text": ch, "key": ch})
                send("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch})
                time.sleep(0.07)
            time.sleep(1.3)
            r = send("Runtime.evaluate", {
                "expression": "document.querySelector('.dd-item')?.click() || 'no-dd'",
                "returnByValue": True})
            print("  dropdown click:", r.get("result", {}).get("value"))

    data = send("Page.captureScreenshot", {"format": "png"})
    if data and "data" in data:
        path = os.path.join(OUT, out_name)
        with open(path, "wb") as f:
            f.write(base64.b64decode(data["data"]))
        print(f"saved {path} ({os.path.getsize(path)} bytes)")

    ws.close()
    proc.terminate()
    time.sleep(1)
    try:
        proc.kill()
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "stock"
    # 先切到行情 tab（搜索框在那里），再搜票进详情
    to_quote = """(() => {
        const nav=[...document.querySelectorAll('.nav-item')];
        const q=nav.find(x=>x.textContent.includes('行情'));
        if(q) q.click();
    })()"""
    search_600060 = """(async () => {
        await new Promise(r=>setTimeout(r,700));
        const inp = document.querySelector('.search-box input');
        if (!inp) return 'no-input';
        inp.value='000001';
        inp.dispatchEvent(new Event('input',{bubbles:true}));
        await new Promise(r=>setTimeout(r,1200));
        const dd = document.querySelector('.dd-item');
        if (dd) dd.click();
        return 'clicked';
    })()"""

    # 用真实 CDP 输入事件，触发 Vue 的 @input
    def type_and_click(ws_send, code):
        """在搜索框输入并点击第一个下拉项"""
        # 聚焦
        ws_send("Runtime.evaluate", {
            "expression": "document.querySelector('.search-box input')?.focus()"})
        time.sleep(0.3)
        # 逐字符输入（触发真实 input 事件）
        for ch in code:
            ws_send("Input.dispatchKeyEvent", {
                "type": "keyDown", "text": ch, "key": ch})
            ws_send("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": ch})
            time.sleep(0.08)
        time.sleep(1.2)
        # 点击下拉第一项
        ws_send("Runtime.evaluate", {
            "expression": "document.querySelector('.dd-item')?.click() || 'no-dd'"})
        time.sleep(3)

    # 从自选 tab 点卡片进详情（最可靠，无需下拉交互）
    to_watch = """(() => {
        const nav=[...document.querySelectorAll('.nav-item')];
        const w=nav.find(x=>x.textContent.includes('自选'));
        if(w) { w.click(); return 'ok'; }
        return 'no-nav';
    })()"""
    click_stock = """(() => {
        const items=[...document.querySelectorAll('.watch-item')];
        const t=items.find(x=>x.textContent.includes('中金岭南')) || items[0];
        if(t){ t.click(); return 'clicked:'+t.textContent.slice(0,10); }
        return 'no-item:'+items.length;
    })()"""

    if target == "stock":
        shot([
            ("eval", to_watch),
            ("wait", 1.5),
            ("eval", click_stock),
            ("wait", 5),
        ], "m4_stock.png")
    elif target == "thesis":
        shot([
            ("eval", to_watch),
            ("wait", 1.5),
            ("eval", click_stock),
            ("wait", 5),
            ("eval", """(() => {
                const tabs=[...document.querySelectorAll('.tab')];
                const t=tabs.find(x=>x.textContent.includes('逻辑'));
                if (t) { t.click(); return 'ok'; }
                return 'tab-not-found';
            })()"""),
            ("wait", 3),
        ], "m4_thesis.png")
    elif target == "notice":
        shot([
            ("eval", to_watch),
            ("wait", 1.5),
            ("eval", click_stock),
            ("wait", 5),
            ("eval", """(() => {
                const tabs=[...document.querySelectorAll('.tab')];
                const t=tabs.find(x=>x.textContent.includes('公告'));
                if (t) { t.click(); return 'ok'; }
                return 'tab-not-found';
            })()"""),
            ("wait", 3),
        ], "m4_notice.png")
