from flask import Flask, request, jsonify, send_file, render_template_string, abort, make_response
from gtts import gTTS
import os
import threading
import time
import re

app = Flask(__name__)

# ================= CONFIG =================
VOICE_DELAY_AFTER_DING_SECONDS = 1.3  # <-- your request (after ding ends)

DESKS = [f"Desk {i}" for i in range(1, 8)]  # 7 desks
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY"

# ================= DATA (thread-safe) =================
lock = threading.Lock()

current_number = 1
desks = {d: "---" for d in DESKS}

last_called = {"number": "001", "desk": "Desk 1"}  # display values
event_id = 0  # increments on NEXT/RECALL/ASSIGN so recall re-speaks

# ================= VOICE CACHE =================
os.makedirs("voices", exist_ok=True)

_voice_file_locks = {}  # filename -> Lock
_voice_file_locks_guard = threading.Lock()


def _safe_filename(s: str) -> str:
    # Keep filenames clean: letters, numbers, underscore, dash
    s = s.strip().lower()
    s = s.replace("go to ", "")
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s or "desk"


def _ensure_voice_lock(filename: str) -> threading.Lock:
    with _voice_file_locks_guard:
        if filename not in _voice_file_locks:
            _voice_file_locks[filename] = threading.Lock()
        return _voice_file_locks[filename]


def _build_voice_text(num_str: str, desk: str) -> str:
    # num_str is like "001" -> int -> "1" (gTTS speaks naturally)
    n = int(num_str)
    return f"Number {n}, please go to {desk}"


def get_voice_file(num_str: str, desk: str) -> str:
    # Only allow known desks (security + stability)
    if desk not in DESKS:
        desk = "Desk 1"

    safe_desk = _safe_filename(desk)
    filename = os.path.join("voices", f"{num_str}_{safe_desk}.mp3")

    lk = _ensure_voice_lock(filename)
    with lk:
        if not os.path.exists(filename):
            text = _build_voice_text(num_str, desk)
            try:
                tts = gTTS(text=text, lang="en")
                tts.save(filename)
            except Exception:
                # If gTTS fails (no internet), we leave file missing; client will fallback to browser TTS
                pass

    return filename


def prewarm_voice_async(num_str: str, desk: str) -> None:
    def _job():
        try:
            get_voice_file(num_str, desk)
        except Exception:
            pass

    threading.Thread(target=_job, daemon=True).start()


def bump_event():
    global event_id
    event_id += 1


# ================= DISPLAY =================
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
let unlocked = false;
let lastEvent = null;

let speakTimer = null;
let announceToken = 0;

// Female-ish browser voice fallback (if mp3 fails)
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
    speechSynthesis.speak(u);
  }catch(e){}
}

// Unlock audio properly
document.getElementById("unlock").addEventListener("click", async () => {
  if (unlocked) return;
  const ding = document.getElementById("ding");
  const voice = document.getElementById("voice");
  try{
    // prime ding
    ding.muted = true;
    await ding.play();
    ding.pause(); ding.currentTime = 0; ding.muted = false;

    // prime voice
    voice.muted = true;
    voice.src = "/voice/001/" + encodeURIComponent("Desk 1");
    voice.load();
    voice.muted = false;

    // prime voices list
    try { speechSynthesis.getVoices(); } catch(e){}

    unlocked = true;
    document.getElementById("unlock").style.display="none";
  }catch(e){}
});

function pad3(s){
  s = String(s);
  return s.length < 3 ? s.padStart(3, "0") : s;
}

// Main announce: ding ends -> wait 1.3s -> voice
async function announce(num, desk){
  if(!unlocked) return;

  announceToken++;
  const myToken = announceToken;

  // cancel old timer/audio/tts
  if (speakTimer){ clearTimeout(speakTimer); speakTimer = null; }
  try { speechSynthesis.cancel(); } catch(e) {}
  const ding = document.getElementById("ding");
  const voice = document.getElementById("voice");

  try { ding.pause(); ding.currentTime = 0; } catch(e){}
  try { voice.pause(); voice.currentTime = 0; } catch(e){}

  // start loading voice immediately (so it can download while ding plays)
  voice.src = "/voice/" + encodeURIComponent(num) + "/" + encodeURIComponent(desk);
  voice.load();

  // play ding and wait for END event
  await new Promise((resolve) => {
    let done = false;
    const finish = () => { if(!done){ done = true; resolve(true); } };

    ding.onended = finish;
    ding.onerror = finish;

    // safety fallback if onended doesn't fire
    setTimeout(finish, 5000);

    const p = ding.play();
    if (p && typeof p.then === "function") p.catch(()=>finish());
  });

  // schedule voice 1.3s after ding ends (exactly from end)
  speakTimer = setTimeout(async () => {
    if (myToken !== announceToken) return;

    try{
      await voice.play();
    }catch(e){
      // fallback to browser TTS if mp3 not ready/blocked
      const n = parseInt(num, 10);
      browserSpeak("Number " + n + ", please go to " + desk);
    }
  }, {{delay_ms}});
}

// Polling
setInterval(()=>{
  fetch("/data", {cache:"no-store"})
    .then(r=>r.json())
    .then(data=>{
      document.getElementById("announcement").innerText = data.announcement;

      document.getElementById("panel").innerHTML =
        Object.entries(data.desks).map(([k,v]) =>
          `<div class="row">${k} <span>${v}</span></div>`
        ).join("");

      // update display every time
      document.getElementById("number").innerText = data.number;
      document.getElementById("desk").innerText = data.desk;

      // announce only when event changes (so recall repeats)
      if (lastEvent === null) lastEvent = data.event_id;
      if (data.event_id !== lastEvent){
        lastEvent = data.event_id;
        announce(data.number, data.desk);
      }
    })
    .catch(()=>{});
}, 900);
</script>

</body>
</html>
"""

# ================= STAFF =================
STAFF_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>STAFF</title>
<style>
body{background:#0f172a;color:white;font-family:Arial;padding:16px;}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
@media(min-width:900px){.grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
.card{background:#1e293b;padding:14px;border-radius:12px;}
h1{margin:0 0 12px 0;}
h3{margin:0 0 8px 0;}
.num{font-size:22px;font-weight:bold;color:#38bdf8;margin:6px 0;}
button{padding:10px;margin-top:8px;border:none;border-radius:10px;font-weight:bold;width:100%;}
.next{background:#22c55e;color:black;}
.recall{background:#3b82f6;color:white;}
.assign{background:#f59e0b;color:black;}
input, select{width:100%;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,.15);background:#0b1220;color:white;margin-top:8px;}
.small{opacity:.8;font-size:12px;margin-top:8px;}
</style>
</head>
<body>

<h1>STAFF CONTROL</h1>

<div class="grid">
{% for d in desks %}
  <div class="card">
    <h3>{{d}}</h3>
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
  <h3>Manual Assign</h3>
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
  <h3>Announcement</h3>
  <form method="post">
    <input name="text" placeholder="New announcement">
    <button class="recall" name="action" value="announce">UPDATE</button>
  </form>
</div>

<div class="small" style="margin-top:12px;">
  Display: <a style="color:#93c5fd" href="/">/</a>
</div>

</body>
</html>
"""

# ================= ROUTES =================
@app.route("/")
def display():
    return render_template_string(DISPLAY_HTML, delay_ms=int(VOICE_DELAY_AFTER_DING_SECONDS * 1000))


@app.route("/staff", methods=["GET", "POST"])
def staff():
    global current_number, announcement

    if request.method == "POST":
        action = request.form.get("action")
        desk = request.form.get("desk")

        if desk not in DESKS:
            desk = DESKS[0]

        with lock:
            if action == "next":
                num = str(current_number).zfill(3)
                desks[desk] = num
                last_called["number"] = num
                last_called["desk"] = desk
                current_number += 1
                bump_event()
                prewarm_voice_async(num, desk)

            elif action == "recall":
                num = desks.get(desk, "---")
                if num != "---":
                    last_called["number"] = num
                    last_called["desk"] = desk
                    bump_event()
                    prewarm_voice_async(num, desk)

            elif action == "assign":
                num = request.form.get("num", "").strip()
                if num.isdigit() and int(num) > 0:
                    n = int(num)
                    num3 = str(n).zfill(3)
                    desks[desk] = num3
                    last_called["number"] = num3
                    last_called["desk"] = desk
                    # prevent duplicates
                    if n >= current_number:
                        current_number = n + 1
                    bump_event()
                    prewarm_voice_async(num3, desk)

            elif action == "announce":
                txt = request.form.get("text", "").strip()
                if txt:
                    announcement = txt

    with lock:
        snapshot = dict(desks)

    return render_template_string(STAFF_HTML, desks=snapshot)


@app.route("/data")
def data():
    with lock:
        return jsonify({
            "number": last_called["number"],
            "desk": last_called["desk"],
            "announcement": announcement,
            "desks": desks,
            "event_id": event_id,
        })


@app.route("/voice/<num>/<path:desk>")
def voice(num, desk):
    # desk arrives URL-decoded by Flask
    fn = get_voice_file(num, desk)
    if not os.path.exists(fn):
        # gTTS failed; return 404 so client falls back to browser TTS
        abort(404)
    resp = make_response(send_file(fn, mimetype="audio/mpeg"))
    # cache OK (same number+desk always same file)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/sound")
def sound():
    if not os.path.exists("dingdong.wav"):
        abort(404)
    resp = make_response(send_file("dingdong.wav", mimetype="audio/wav"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/logo")
def logo():
    if not os.path.exists("logo.gif"):
        abort(404)
    resp = make_response(send_file("logo.gif", mimetype="image/gif"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
