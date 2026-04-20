from __future__ import annotations

import os
import re
import time
import threading
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template_string, abort, make_response

# ===================== APP =====================
app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

# ===================== CONFIG =====================
VOICE_DELAY_AFTER_DING_SECONDS = 1.3  # speak 1.3s AFTER ding ends (front-end controlled)
DESKS = [f"Desk {i}" for i in range(1, 8)]  # 7 desks
DEFAULT_ANNOUNCEMENT = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY"

# ===================== STATE (THREAD SAFE) =====================
lock = threading.Lock()
current_number = 1
announcement = DEFAULT_ANNOUNCEMENT
desks = {d: "---" for d in DESKS}
last_called = {"number": "001", "desk": "Desk 1"}
call_id = 0  # increments on NEXT/RECALL/ASSIGN so display re-announces even if number repeats

# ===================== VOICE CACHE (gTTS) =====================
# NOTE: gTTS needs internet. If gTTS fails, display will fall back to device voice.
VOICES_DIR = BASE_DIR / "voices"
VOICES_DIR.mkdir(exist_ok=True)

_voice_locks = {}
_voice_locks_guard = threading.Lock()


def _safe_filename(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s or "desk"


def _get_file_lock(path: Path) -> threading.Lock:
    k = str(path)
    with _voice_locks_guard:
        if k not in _voice_locks:
            _voice_locks[k] = threading.Lock()
        return _voice_locks[k]


def voice_path(num: str, desk: str) -> Path:
    # normalize desk
    if desk not in DESKS:
        desk = "Desk 1"
    return VOICES_DIR / f"{num}_{_safe_filename(desk)}.mp3"


def build_voice(num: str, desk: str) -> Path | None:
    """
    Creates cached mp3 if missing. Returns path if exists, else None.
    """
    p = voice_path(num, desk)
    lk = _get_file_lock(p)

    with lk:
        if p.exists():
            return p

        try:
            from gtts import gTTS  # import only when needed

            text = f"Number {int(num)}, please go to {desk}"
            tts = gTTS(text=text, lang="en")
            tts.save(str(p))
            return p if p.exists() else None
        except Exception:
            # gTTS blocked or no internet -> caller will fallback to device voice
            return None


def prewarm_voice_async(num: str, desk: str) -> None:
    threading.Thread(target=build_voice, args=(num, desk), daemon=True).start()


# ===================== HELPERS =====================
def bump_call_id() -> None:
    global call_id
    call_id += 1


def asset(name: str) -> Path:
    return BASE_DIR / name


# ===================== DISPLAY =====================
DISPLAY_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>QUEUE DISPLAY</title>
<style>
  body {margin:0;font-family:Arial;text-align:center;background:white;}
  .top {background:#dc2626;color:white;padding:12px;font-size:22px;font-weight:bold;}
  .number {font-size:160px;color:#dc2626;text-shadow:4px 4px black;}
  .desk {font-size:50px;margin-bottom:20px;font-weight:bold;}
  .panel {position:fixed;right:0;top:60px;width:300px;background:#f3f4f6;padding:12px;border-left:1px solid #e5e7eb;height:calc(100vh - 60px);overflow:auto;}
  .row {display:flex;justify-content:space-between;margin:8px 0;font-weight:bold;}
  .row span {color:#dc2626;}
  .logo {position:fixed;bottom:10px;left:10px;width:120px;}

  .overlay {
    position:fixed;top:0;left:0;width:100%;height:100%;
    background:rgba(0,0,0,.92);color:white;display:flex;
    justify-content:center;align-items:center;flex-direction:column;
    font-size:24px;z-index:9999;text-align:center;padding:20px;box-sizing:border-box;
    cursor:pointer;
  }
  .btn {background:#dc2626;padding:12px 18px;border-radius:10px;margin-top:14px;font-weight:bold;}
  .small {opacity:.75;font-size:14px;margin-top:10px;line-height:1.3;}
</style>
</head>
<body>

<div class="overlay" id="unlock">
  <div>TAP TO ENABLE SOUND</div>
  <div class="btn">ENABLE AUDIO</div>
  <div class="small">
    Android blocks autoplay audio/voice until you tap once.<br/>
    After enabling, ding + voice will work.
  </div>
</div>

<div class="top" id="announcement"></div>
<div class="number" id="number">001</div>
<div class="desk" id="desk">Desk 1</div>

<div class="panel" id="panel"></div>
<img src="/logo" class="logo"/>

<audio id="ding" src="/sound" preload="auto"></audio>
<audio id="voice" preload="auto"></audio>

<script>
  const VOICE_DELAY_MS = {{ delay_ms }};

  let unlocked = false;
  let lastCallId = -1;

  let speakTimer = null;
  let announceToken = 0;

  const ding = document.getElementById("ding");
  const voice = document.getElementById("voice");

  function pickVoice() {
    const voices = speechSynthesis.getVoices() || [];
    if (!voices.length) return null;
    const prefer = [
      v => v.name.toLowerCase().includes("zira"),
      v => v.name.toLowerCase().includes("female"),
      v => v.name.toLowerCase().includes("google uk english female"),
      v => v.lang.toLowerCase().startsWith("en"),
    ];
    for (const rule of prefer) {
      const f = voices.find(rule);
      if (f) return f;
    }
    return voices[0];
  }

  function browserSpeak(text){
    try{
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const v = pickVoice();
      if (v) u.voice = v;
      u.rate = 0.92;
      u.pitch = 1.0;
      speechSynthesis.speak(u);
    }catch(e){}
  }

  async function safePlay(aud){
    try { await aud.play(); return true; } catch(e) { return false; }
  }

  function stopAll(){
    if (speakTimer){ clearTimeout(speakTimer); speakTimer = null; }
    try { speechSynthesis.cancel(); } catch(e){}
    try { ding.pause(); ding.currentTime = 0; } catch(e){}
    try { voice.pause(); voice.currentTime = 0; } catch(e){}
  }

  // Unlock audio
  document.getElementById("unlock").addEventListener("click", async () => {
    if (unlocked) return;
    try{
      // prime ding
      ding.muted = true;
      await safePlay(ding);
      ding.pause(); ding.currentTime = 0; ding.muted = false;

      // prime voices list
      try { speechSynthesis.getVoices(); } catch(e){}

      unlocked = true;
      document.getElementById("unlock").style.display="none";
    }catch(e){}
  });

  async function announce(num, desk){
    if (!unlocked) return;

    announceToken++;
    const myToken = announceToken;

    stopAll();

    // Start loading mp3 immediately (downloads while ding plays)
    voice.src = "/voice/" + encodeURIComponent(num) + "/" + encodeURIComponent(desk) + "?t=" + Date.now();
    voice.load();

    // Play ding and wait for it to finish
    await new Promise(async (resolve) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(true); } };

      ding.onended = finish;
      ding.onerror = finish;

      // fallback safety
      setTimeout(finish, 5000);

      await safePlay(ding);
    });

    // Speak 1.3s after ding ENDS
    speakTimer = setTimeout(async () => {
      if (myToken !== announceToken) return;

      const ok = await safePlay(voice);
      if (!ok) {
        const n = parseInt(num, 10);
        browserSpeak("Number " + n + ", please go to " + desk);
      }
    }, VOICE_DELAY_MS);
  }

  setInterval(() => {
    fetch("/data", {cache:"no-store"})
      .then(r => r.json())
      .then(data => {
        document.getElementById("announcement").innerText = data.announcement;

        document.getElementById("panel").innerHTML =
          Object.entries(data.desks).map(([k,v]) =>
            `<div class="row">${k} <span>${v}</span></div>`
          ).join("");

        document.getElementById("number").innerText = data.number;
        document.getElementById("desk").innerText = data.desk;

        if (data.call_id !== lastCallId) {
          lastCallId = data.call_id;
          announce(data.number, data.desk);
        }
      })
      .catch(()=>{});
  }, 900);
</script>
</body>
</html>
"""

# ===================== STAFF =====================
STAFF_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>STAFF</title>
<style>
  body{background:#0f172a;color:white;font-family:Arial;padding:16px;}
  h1{margin:0 0 12px 0;}
  .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
  @media(min-width:900px){.grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
  .card{background:#1e293b;padding:14px;border-radius:12px;}
  .num{font-size:22px;font-weight:bold;color:#38bdf8;margin:6px 0;}
  button{padding:10px;margin-top:8px;border:none;border-radius:10px;font-weight:bold;width:100%;}
  .next{background:#22c55e;color:black;}
  .recall{background:#3b82f6;color:white;}
  .assign{background:#f59e0b;color:black;}
  .danger{background:#ef4444;color:white;}
  input, select{width:100%;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,.15);background:#0b1220;color:white;margin-top:8px;}
  .small{opacity:.8;font-size:12px;margin-top:8px;line-height:1.3;}
</style>
</head>
<body>

<h1>STAFF CONTROL</h1>

<div class="grid">
{% for d in desks %}
  <div class="card">
    <b>{{d}}</b>
    <div class="num">{{desks[d]}}</div>
    <form method="post">
      <input type="hidden" name="desk" value="{{d}}">
      <button class="next" name="action" value="next">NEXT</button>
      <button class="recall" name="action" value="recall">RECALL</button>
    </form>
  </div>
{% endfor %}
</div>

<div class="card" style="margin-top:12px;">
  <b>Manual Assign</b>
  <form method="post">
    <input name="num" placeholder="Enter number (e.g., 120)">
    <select name="desk">
      {% for d in desks %}<option value="{{d}}">{{d}}</option>{% endfor %}
    </select>
    <button class="assign" name="action" value="assign">ASSIGN</button>
    <div class="small">If you assign 120, NEXT becomes 121 automatically.</div>
  </form>
</div>

<div class="card" style="margin-top:12px;">
  <b>Announcement</b>
  <form method="post">
    <input name="text" placeholder="New announcement">
    <button class="recall" name="action" value="announce">UPDATE</button>
  </form>
</div>

<div class="card" style="margin-top:12px;">
  <b>System</b>
  <form method="post">
    <button class="danger" name="action" value="reset" onclick="return confirm('Reset all desks and restart from 001?')">RESET</button>
  </form>
</div>

</body>
</html>
"""


@app.route("/")
def display():
    return render_template_string(DISPLAY_HTML, delay_ms=int(VOICE_DELAY_AFTER_DING_SECONDS * 1000))


@app.route("/staff", methods=["GET", "POST"])
def staff():
    global current_number, announcement

    if request.method == "POST":
        action = request.form.get("action", "")
        desk = request.form.get("desk", "")

        if desk not in DESKS:
            desk = DESKS[0]

        with lock:
            if action == "next":
                num = str(current_number).zfill(3)
                desks[desk] = num
                last_called["number"] = num
                last_called["desk"] = desk
                current_number += 1
                bump_call_id()
                prewarm_voice_async(num, desk)

            elif action == "recall":
                num = desks.get(desk, "---")
                if num != "---":
                    last_called["number"] = num
                    last_called["desk"] = desk
                    bump_call_id()
                    prewarm_voice_async(num, desk)

            elif action == "assign":
                raw = request.form.get("num", "").strip()
                if raw.isdigit() and int(raw) > 0:
                    n = int(raw)
                    num3 = str(n).zfill(3)
                    desks[desk] = num3
                    last_called["number"] = num3
                    last_called["desk"] = desk
                    if n >= current_number:
                        current_number = n + 1
                    bump_call_id()
                    prewarm_voice_async(num3, desk)

            elif action == "announce":
                txt = request.form.get("text", "").strip()
                if txt:
                    announcement = txt

            elif action == "reset":
                current_number = 1
                announcement = DEFAULT_ANNOUNCEMENT
                for d in DESKS:
                    desks[d] = "---"
                last_called["number"] = "001"
                last_called["desk"] = "Desk 1"
                bump_call_id()

    with lock:
        snapshot = dict(desks)

    return render_template_string(STAFF_HTML, desks=snapshot)


@app.route("/data")
def data():
    with lock:
        return jsonify(
            number=last_called["number"],
            desk=last_called["desk"],
            announcement=announcement,
            desks=desks,
            call_id=call_id,
        )


@app.route("/voice/<num>/<path:desk>")
def voice(num, desk):
    # Build (or reuse) cached mp3
    p = build_voice(num, desk)
    if p is None or (not p.exists()):
        abort(404)

    resp = make_response(send_file(str(p), mimetype="audio/mpeg"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/sound")
def sound():
    p = asset("dingdong.wav")
    if not p.exists():
        abort(404)
    resp = make_response(send_file(str(p), mimetype="audio/wav"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/logo")
def logo():
    p = asset("logo.gif")
    if not p.exists():
        abort(404)
    resp = make_response(send_file(str(p), mimetype="image/gif"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


if __name__ == "__main__":
    # Render uses PORT env var
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
