from __future__ import annotations

import socket
import time
import threading
from pathlib import Path
from typing import Dict, Any

from flask import Flask, render_template_string, request, jsonify, send_file, abort, make_response

# ============================================================
# TELECEL QUEUE (WEB / ANDROID CAST VERSION) — 7 DESKS
# FIX: Voice speaks ~1.3s after the DING *AUDIBLE END*
#      (no extra voice-loading wait; no lag/backlog).
#
# Place next to this file:
#   - dingdong.wav
#   - logo.gif
#
# Run:
#   pip install flask
#   python TQMS.py
# Open on phones (same Wi‑Fi):
#   http://PC_IP:5000/display
#   http://PC_IP:5000/staff
# ============================================================

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

APP_NAME = "TELECEL QUEUE"
DESK_NAMES = [f"Desk {i}" for i in range(1, 8)]  # 7 desks

# Speech timing request:
VOICE_DELAY_AFTER_DING_SECONDS = 1.3

# --------------------- Thread-safe state ---------------------
lock = threading.Lock()
state: Dict[str, Any] = {
    "current_number": 1,  # infinite
    "announcement": "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY •",
    "desks": {d: None for d in DESK_NAMES},  # desk -> int | None
    "last_called": {"number": 1, "desk_line": "WELCOME"},  # number int, desk_line string
    "history": [],  # list of {"t": "...", "num": int, "desk": str}
    "event_id": 0,  # increments on every NEXT/RECALL/ASSIGN so recall re-announces
}


def fmt_display(n: int) -> str:
    s = str(int(n))
    return s.zfill(3) if len(s) < 3 else s


def now_str() -> str:
    return time.strftime("%H:%M:%S")


def bump_event() -> None:
    state["event_id"] += 1


def push_history(num: int, desk: str) -> None:
    state["history"].insert(0, {"t": now_str(), "num": int(num), "desk": desk})
    state["history"] = state["history"][:10]


# --------------------- Network helper (LAN IP) ---------------------
def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def base_url() -> str:
    return f"http://{get_lan_ip()}:5000"


def asset_path(name: str) -> Path:
    return BASE_DIR / name


# ============================================================
# DISPLAY (cast/mirror this page to shop TV)
# Uses Web Audio API to:
#  - load ding once
#  - compute audible end (trims trailing silence)
#  - schedule voice 1.3s after audible end
# ============================================================
DISPLAY_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{app_name}} • DISPLAY</title>
  <style>
    :root{ --red:#dc2626; --ink:#0f172a; --panel:#f8fafc; }
    body{ margin:0; font-family: Arial, Helvetica, sans-serif; background:#fff; }
    .top{
      background:var(--red); color:#fff; height:46px; display:flex; align-items:center;
      overflow:hidden; white-space:nowrap; padding:0 12px; font-weight:900;
    }
    .marquee{ display:inline-block; padding-left:100%; animation: scroll 14s linear infinite; font-size:16px; }
    @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-100%);} }

    .main{ display:flex; height:calc(100vh - 46px); }
    .left{ flex:5; display:flex; flex-direction:column; align-items:center; justify-content:center; }
    .right{ flex:2; background:var(--panel); padding:14px; box-sizing:border-box; overflow:auto; }

    .numberWrap{ height:250px; display:flex; align-items:center; justify-content:center; }
    .bigStack{ position:relative; line-height:1; }
    .bigText{ font-size:170px; font-weight:900; color:var(--red); text-align:center; }
    .outline{ position:absolute; left:0; top:0; color:#000; z-index:0; }
    .front{ position:relative; z-index:1; }

    .deskLine{ font-size:52px; font-weight:900; color:#111; text-align:center; margin-top:8px; padding:0 16px; }

    .logo{ position:fixed; bottom:12px; left:12px; width:120px; height:auto; }

    .panelTitle{ font-weight:900; color:var(--ink); margin:8px 0 10px; }
    .deskRow{
      background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:12px;
      padding:10px 12px; margin-bottom:10px; display:flex; align-items:center;
    }
    .deskRow b{ font-size:12px; letter-spacing:.5px; }
    .deskRow .val{ margin-left:auto; font-weight:900; color:var(--red); font-size:16px; }

    .historyLine{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size:12px; padding:3px 0; color:#111827;
    }

    .tiny{ color:rgba(0,0,0,.55); font-size:12px; margin-top:10px; }

    /* Android autoplay unlock overlay */
    .overlay{
      position:fixed; inset:0; background:rgba(15,23,42,.92);
      display:flex; align-items:center; justify-content:center;
      z-index:9999; color:#fff; text-align:center; padding:20px; box-sizing:border-box;
    }
    .card{
      width:min(520px, 92vw);
      background:rgba(30,41,59,.85);
      border:1px solid rgba(255,255,255,.08);
      border-radius:16px;
      padding:18px;
    }
    .btn{
      display:inline-block; background:var(--red);
      padding:14px 18px; border-radius:12px;
      font-weight:900; margin-top:12px; cursor:pointer; user-select:none;
    }
    .hint{ color:rgba(255,255,255,.75); margin-top:10px; font-size:13px; line-height:1.35; }

    @media (max-width: 900px){
      .main{ flex-direction:column; }
      .right{ order:2; height:40vh; }
      .left{ order:1; height:60vh; }
      .bigText{ font-size:140px; }
      .deskLine{ font-size:38px; }
      .logo{ width:100px; }
    }
  </style>
</head>
<body>
  <div class="top"><span class="marquee" id="marquee">LOADING…</span></div>

  <div class="main">
    <div class="left">
      <div class="numberWrap">
        <div class="bigStack">
          <div class="bigText outline" style="transform:translate(-3px,-3px)" id="o1">000</div>
          <div class="bigText outline" style="transform:translate( 3px,-3px)" id="o2">000</div>
          <div class="bigText outline" style="transform:translate(-3px, 3px)" id="o3">000</div>
          <div class="bigText outline" style="transform:translate( 3px, 3px)" id="o4">000</div>
          <div class="bigText front" id="number">000</div>
        </div>
      </div>

      <div class="deskLine" id="desk">WELCOME</div>

      <img src="/logo" class="logo" alt="Telecel Logo" />
    </div>

    <div class="right">
      <div class="panelTitle">LIVE DESKS</div>
      <div id="liveDesks"></div>

      <div class="panelTitle" style="margin-top:16px;">LAST CALLS</div>
      <div id="history"></div>

      <div class="tiny" id="status">Starting…</div>
      <div class="tiny">STAFF: <b>{{base_url}}/staff</b></div>
    </div>
  </div>

  <div class="overlay" id="unlock">
    <div class="card">
      <div style="font-size:20px; font-weight:900;">TAP TO ENABLE SOUND</div>
      <div class="hint">
        Android browsers block autoplay audio and voice until you tap once.
        After you tap, dingdong + voice announcements will work.
      </div>
      <div class="btn" id="unlockBtn">ENABLE AUDIO</div>
    </div>
  </div>

<script>
  // ------------------------------------------------------------
  // Timing goal:
  //   Voice starts 1.3 seconds AFTER the DING *AUDIBLE END*.
  // We use Web Audio to decode the wav and compute audible end
  // (trims trailing silence), then schedule voice.
  // Latest-wins (no backlog): new call cancels prior timers/audio/voice.
  // ------------------------------------------------------------

  const VOICE_DELAY_AFTER_DING = {{ voice_delay }}; // seconds

  let audioUnlocked = false;
  let lastEventId = null;

  // latest-wins token + timer
  let announceToken = 0;
  let speakTimer = null;
  let pendingText = null;

  // Web Audio
  let audioCtx = null;
  let dingBuffer = null;
  let dingAudibleSeconds = null;
  let currentSource = null;

  function pad3(x){ x = String(x); return x.length < 3 ? x.padStart(3,'0') : x; }

  // ---- SpeechSynthesis voice ----
  function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || [];
    if (!voices.length) return null;

    const preferred = [
      v => v.name.toLowerCase().includes("zira"),
      v => v.name.toLowerCase().includes("female"),
      v => v.name.toLowerCase().includes("google uk english female"),
      v => v.lang.toLowerCase().startsWith("en") && v.name.toLowerCase().includes("google"),
      v => v.lang.toLowerCase().startsWith("en"),
    ];
    for (const rule of preferred) {
      const found = voices.find(rule);
      if (found) return found;
    }
    return voices[0];
  }

  function warmVoices() {
    try { window.speechSynthesis.getVoices(); } catch(e) {}
  }

  function speak(text) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const voice = pickVoice();
      if (voice) u.voice = voice;
      u.rate = 0.92;
      u.pitch = 1.0;
      window.speechSynthesis.speak(u);
    } catch(e) {}
  }

  // ---- Compute audible duration by trimming trailing silence ----
  function computeAudibleSeconds(buffer) {
    try {
      const sr = buffer.sampleRate;
      const ch = buffer.numberOfChannels;
      const threshold = 0.02; // amplitude in [-1..1]
      let lastIndex = 0;

      for (let c = 0; c < ch; c++) {
        const data = buffer.getChannelData(c);
        for (let i = data.length - 1; i >= 0; i--) {
          if (Math.abs(data[i]) > threshold) {
            if (i > lastIndex) lastIndex = i;
            break;
          }
        }
      }

      // Convert sample index to seconds, add tiny safety pad
      const t = (lastIndex + 1) / sr;
      const padded = Math.min(buffer.duration, t + 0.05);
      // Keep a sane minimum
      return Math.max(0.05, padded);
    } catch(e) {
      return buffer.duration || 1.0;
    }
  }

  async function loadDing() {
    // Fetch wav and decode once
    const res = await fetch("/sound", { cache: "no-store" });
    const arr = await res.arrayBuffer();
    dingBuffer = await audioCtx.decodeAudioData(arr);
    dingAudibleSeconds = computeAudibleSeconds(dingBuffer);
  }

  function stopAudioAndTimers() {
    // cancel speak timer
    if (speakTimer) { clearTimeout(speakTimer); speakTimer = null; }

    // stop speech
    try { window.speechSynthesis.cancel(); } catch(e) {}

    // stop current web-audio source
    try {
      if (currentSource) {
        currentSource.stop(0);
        currentSource.disconnect();
      }
    } catch(e) {}
    currentSource = null;
  }

  function playDing() {
    const src = audioCtx.createBufferSource();
    src.buffer = dingBuffer;
    src.connect(audioCtx.destination);
    src.start(0);
    currentSource = src;
    return audioCtx.currentTime; // start time
  }

  async function dingThenSpeak(text) {
    announceToken++;
    const myToken = announceToken;

    if (!audioUnlocked) { pendingText = text; return; }
    pendingText = null;

    stopAudioAndTimers();
    warmVoices();

    if (!dingBuffer) {
      // should not happen, but safe
      return;
    }

    const startAt = playDing();
    const speakAt = startAt + (dingAudibleSeconds || 0) + VOICE_DELAY_AFTER_DING;

    const ms = Math.max(0, (speakAt - audioCtx.currentTime) * 1000);

    speakTimer = setTimeout(() => {
      if (myToken !== announceToken) return;
      speak(text);
    }, ms);
  }

  async function unlockAudio() {
    audioUnlocked = true;
    document.getElementById("unlock").style.display = "none";

    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    try { await audioCtx.resume(); } catch(e) {}

    // Load ding + compute audible end (no lag later)
    try {
      await loadDing();
    } catch(e) {
      // If load fails, keep overlay hidden but you won't get ding
      console.log("ding load failed", e);
    }

    warmVoices();

    if (pendingText) {
      const t = pendingText;
      pendingText = null;
      dingThenSpeak(t);
    }
  }

  document.getElementById("unlockBtn").addEventListener("click", unlockAudio);
  document.getElementById("unlock").addEventListener("click", unlockAudio);

  // ---- Render helpers ----
  function renderLiveDesks(desks){
    const wrap = document.getElementById("liveDesks");
    wrap.innerHTML = "";
    Object.keys(desks).forEach(d => {
      const v = desks[d] == null ? "---" : pad3(desks[d]);
      const row = document.createElement("div");
      row.className = "deskRow";
      row.innerHTML = `<b>${d.toUpperCase()}</b><div class="val">${v}</div>`;
      wrap.appendChild(row);
    });
  }

  function renderHistory(hist){
    const wrap = document.getElementById("history");
    wrap.innerHTML = "";
    hist.slice(0,8).forEach(h => {
      const line = document.createElement("div");
      line.className = "historyLine";
      line.textContent = `${h.t}  ${pad3(h.num)}  →  ${h.desk}`;
      wrap.appendChild(line);
    });
  }

  function setBig(numDisplay){
    document.getElementById("number").innerText = numDisplay;
    document.getElementById("o1").innerText = numDisplay;
    document.getElementById("o2").innerText = numDisplay;
    document.getElementById("o3").innerText = numDisplay;
    document.getElementById("o4").innerText = numDisplay;
  }

  async function poll(){
    try{
      const res = await fetch("/api/state", { cache: "no-store" });
      const data = await res.json();

      document.getElementById("marquee").innerText = data.announcement;

      setBig(data.last_called_display);
      document.getElementById("desk").innerText = data.last_called_desk_line;

      renderLiveDesks(data.desks);
      renderHistory(data.history);

      document.getElementById("status").innerText =
        `Online • event ${data.event_id} • next ${pad3(data.current_number)} • Server {{base_url}} • voice +${VOICE_DELAY_AFTER_DING}s`;

      if (lastEventId === null) lastEventId = data.event_id;

      if (data.event_id !== lastEventId) {
        lastEventId = data.event_id;
        const speakNum = String(data.last_called_number); // natural
        const speakDeskLine = data.last_called_desk_line.replace("GO TO ", "Please go to ");
        await dingThenSpeak(`Number ${speakNum}. ${speakDeskLine}.`);
      }

    }catch(e){
      document.getElementById("status").innerText = "Offline… check Wi‑Fi/server";
    } finally {
      setTimeout(poll, 650);
    }
  }

  poll();
</script>
</body>
</html>
"""

# ============================================================
# STAFF (control panel)
# ============================================================
STAFF_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{app_name}} • STAFF</title>
  <style>
    :root{
      --bg:#0f172a; --panel:#1e293b; --red:#dc2626;
      --good:#22c55e; --blue:#3b82f6; --orange:#f59e0b;
    }
    body{ margin:0; font-family: Arial, Helvetica, sans-serif; background:var(--bg); color:#fff; }
    .wrap{ padding:14px; max-width:1100px; margin:0 auto; }
    .topbar{
      display:flex; align-items:center; gap:12px; flex-wrap:wrap;
      padding:12px; background:var(--panel); border-radius:14px;
      border:1px solid rgba(255,255,255,.05);
    }
    .topbar h1{ margin:0; font-size:20px; font-weight:900; }
    .pill{ margin-left:auto; color:#cbd5e1; font-weight:900; }
    .grid{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:12px; margin-top:12px; }
    @media (min-width: 900px){ .grid{ grid-template-columns: repeat(4, minmax(0,1fr)); } }

    .tile{ background:var(--panel); border-radius:14px; padding:12px; border:1px solid rgba(255,255,255,.05); }
    .tile .desk{ font-weight:900; }
    .tile .num{ font-size:26px; font-weight:900; color:#38bdf8; margin-top:6px; }

    button{
      width:100%; border:none; padding:10px 12px; border-radius:12px;
      font-weight:900; cursor:pointer; margin-top:8px; font-size:15px;
    }
    .next{ background:var(--good); color:#000; }
    .recall{ background:var(--blue); color:#fff; }

    .row{ display:flex; gap:12px; flex-wrap:wrap; margin-top:12px; }
    .box{
      flex:1; min-width:280px;
      background:var(--panel); border-radius:14px; padding:12px;
      border:1px solid rgba(255,255,255,.05);
    }
    input, select{
      width:100%; padding:10px; border-radius:10px;
      border:1px solid rgba(255,255,255,.12);
      background:#0b1220; color:#fff; outline:none; margin-top:8px;
    }
    .btnOrange{ background:var(--orange); color:#000; }
    .btnRed{ background:#ef4444; color:#fff; }
    .btnBlue{ background:var(--blue); color:#fff; }
    .hint{ color:#cbd5e1; font-size:12px; margin-top:8px; line-height:1.35; }
    .err{ color:#fecaca; font-size:12px; margin-top:8px; white-space:pre-wrap; }
    a{ color:#93c5fd; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <h1>STAFF CONTROL</h1>
      <div class="pill">NEXT: <span id="nextNum">---</span></div>
      <div style="color:#cbd5e1; font-size:12px;">
        Display: <a href="/display" target="_blank">/display</a> • Server: <b>{{base_url}}</b>
      </div>
    </div>

    <div class="grid" id="deskGrid"></div>

    <div class="row">
      <div class="box">
        <div style="font-weight:900;">MANUAL ASSIGN</div>
        <input id="manualNum" placeholder="Enter number (e.g., 120)" inputmode="numeric" />
        <select id="manualDesk"></select>
        <button class="btnOrange" onclick="manualAssign()">ASSIGN</button>
        <div class="hint">If you assign 120, NEXT becomes 121 automatically.</div>
        <div class="err" id="err1"></div>
      </div>

      <div class="box">
        <div style="font-weight:900; color:#fde047;">ANNOUNCEMENT</div>
        <input id="announce" placeholder="New announcement text..." />
        <button class="btnBlue" onclick="updateAnnouncement()">UPDATE</button>

        <button class="btnRed" style="margin-top:14px;" onclick="resetAll()">RESET SYSTEM</button>
        <div class="hint">Reset clears desks and restarts from 001.</div>
        <div class="err" id="err2"></div>
      </div>
    </div>
  </div>

<script>
  let desks = {};
  function pad3(x){ x = String(x); return x.length < 3 ? x.padStart(3,'0') : x; }

  function render(){
    const grid = document.getElementById("deskGrid");
    grid.innerHTML = "";

    Object.keys(desks).forEach(d => {
      const val = desks[d] == null ? "---" : pad3(desks[d]);
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.innerHTML = `
        <div class="desk">${d}</div>
        <div class="num">${val}</div>
        <button class="next" onclick="act('next','${d}')">NEXT</button>
        <button class="recall" onclick="act('recall','${d}')">RECALL</button>
      `;
      grid.appendChild(tile);
    });

    const sel = document.getElementById("manualDesk");
    if (!sel.options.length) {
      Object.keys(desks).forEach(d => {
        const o = document.createElement("option");
        o.value = d; o.textContent = d;
        sel.appendChild(o);
      });
    }
  }

  async function refresh(){
    const res = await fetch("/api/state", {cache:"no-store"});
    const data = await res.json();
    desks = data.desks;
    document.getElementById("nextNum").innerText = pad3(data.current_number);

    const a = document.getElementById("announce");
    if (document.activeElement !== a) a.value = data.announcement;

    render();
  }

  async function act(action, desk){
    document.getElementById("err1").innerText = "";
    document.getElementById("err2").innerText = "";
    const res = await fetch("/api/action", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({action, desk})
    });
    const out = await res.json().catch(()=>({}));
    if (!res.ok) document.getElementById("err2").innerText = out.error || "Action failed";
    refresh();
  }

  async function manualAssign(){
    document.getElementById("err1").innerText = "";
    const n = document.getElementById("manualNum").value.trim();
    const desk = document.getElementById("manualDesk").value;

    const res = await fetch("/api/action", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({action:"assign", desk, number:n})
    });
    const out = await res.json().catch(()=>({}));
    if (!res.ok) {
      document.getElementById("err1").innerText = out.error || "Assign failed";
      return;
    }
    document.getElementById("manualNum").value = "";
    refresh();
  }

  async function updateAnnouncement(){
    document.getElementById("err2").innerText = "";
    const t = document.getElementById("announce").value.trim();
    const res = await fetch("/api/action", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({action:"update_announcement", text:t})
    });
    const out = await res.json().catch(()=>({}));
    if (!res.ok) document.getElementById("err2").innerText = out.error || "Update failed";
    refresh();
  }

  async function resetAll(){
    document.getElementById("err2").innerText = "";
    if (!confirm("Reset all desks and restart numbering from 001?")) return;

    const res = await fetch("/api/action", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({action:"reset"})
    });
    const out = await res.json().catch(()=>({}));
    if (!res.ok) document.getElementById("err2").innerText = out.error || "Reset failed";
    refresh();
  }

  refresh();
  setInterval(refresh, 1500);
</script>
</body>
</html>
"""

# ============================================================
# ROUTES
# ============================================================
@app.get("/")
def home():
    return f"""
    <h2>{APP_NAME}</h2>
    <p><b>Server:</b> {base_url()}</p>
    <ul>
      <li><a href="/display">/display</a> (cast/mirror this to TV)</li>
      <li><a href="/staff">/staff</a> (control from phone)</li>
    </ul>
    <p><b>Voice timing:</b> {VOICE_DELAY_AFTER_DING_SECONDS}s after ding audible end</p>
    """


@app.get("/display")
def display():
    return render_template_string(
        DISPLAY_HTML,
        app_name=APP_NAME,
        base_url=base_url(),
        voice_delay=VOICE_DELAY_AFTER_DING_SECONDS,
    )


@app.get("/staff")
def staff():
    return render_template_string(STAFF_HTML, app_name=APP_NAME, base_url=base_url())


@app.get("/api/state")
def api_state():
    with lock:
        last_num = int(state["last_called"]["number"])
        resp = {
            "current_number": int(state["current_number"]),
            "announcement": str(state["announcement"]),
            "desks": dict(state["desks"]),
            "history": list(state["history"]),
            "event_id": int(state["event_id"]),
            "last_called_number": last_num,               # natural (for voice)
            "last_called_display": fmt_display(last_num), # padded (for screen)
            "last_called_desk_line": str(state["last_called"]["desk_line"]),
        }
    r = jsonify(resp)
    r.headers["Cache-Control"] = "no-store"
    return r


@app.post("/api/action")
def api_action():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip().lower()
    desk = str(data.get("desk", "")).strip()

    with lock:
        if action in ("next", "recall", "assign") and desk not in state["desks"]:
            return jsonify({"ok": False, "error": "Unknown desk"}), 400

        if action == "next":
            n = int(state["current_number"])
            state["desks"][desk] = n
            state["last_called"] = {"number": n, "desk_line": f"GO TO {desk}"}
            push_history(n, desk)
            state["current_number"] = n + 1
            bump_event()
            return jsonify({"ok": True})

        if action == "recall":
            n = state["desks"].get(desk)
            if n is None:
                return jsonify({"ok": True, "note": "Nothing to recall"})
            state["last_called"] = {"number": int(n), "desk_line": f"GO TO {desk}"}
            push_history(int(n), desk)
            bump_event()
            return jsonify({"ok": True})

        if action == "assign":
            raw = str(data.get("number", "")).strip()
            if not raw.isdigit() or int(raw) <= 0:
                return jsonify({"ok": False, "error": "Enter a valid positive number (e.g., 120)"}), 400
            n = int(raw)
            state["desks"][desk] = n
            state["last_called"] = {"number": n, "desk_line": f"GO TO {desk}"}
            push_history(n, desk)
            if n >= int(state["current_number"]):
                state["current_number"] = n + 1
            bump_event()
            return jsonify({"ok": True})

        if action == "update_announcement":
            text = str(data.get("text", "")).strip()
            if not text:
                return jsonify({"ok": False, "error": "Announcement cannot be empty"}), 400
            state["announcement"] = text
            return jsonify({"ok": True})

        if action == "reset":
            state["current_number"] = 1
            state["announcement"] = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY •"
            state["desks"] = {d: None for d in DESK_NAMES}
            state["last_called"] = {"number": 1, "desk_line": "WELCOME"}
            state["history"] = []
            bump_event()
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": "Unknown action"}), 400


@app.get("/sound")
def sound():
    p = asset_path("dingdong.wav")
    if not p.exists():
        abort(404, "dingdong.wav not found next to the .py file")
    resp = make_response(send_file(str(p), mimetype="audio/wav"))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/logo")
def logo():
    p = asset_path("logo.gif")
    if not p.exists():
        abort(404, "logo.gif not found next to the .py file")
    resp = make_response(send_file(str(p), mimetype="image/gif"))
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
