from flask import Flask, request, jsonify, send_file, render_template_string
from gtts import gTTS
import os

app = Flask(__name__)

# ================= DATA =================
current_number = 1
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY"

DESKS = [f"Desk {i}" for i in range(1, 8)]
desks = {d: "---" for d in DESKS}

last_called = {"number": "001", "desk": "Desk 1"}
call_id = 0

os.makedirs("voices", exist_ok=True)

# ================= VOICE =================
def get_voice(num, desk):
    filename = f"voices/{num}_{desk}.mp3"

    if not os.path.exists(filename):
        text = f"Number {int(num)}, please go to {desk}"
        tts = gTTS(text=text, lang="en")
        tts.save(filename)

    return filename

# ================= DISPLAY =================
@app.route("/")
def display():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<title>QUEUE DISPLAY</title>

<style>
body {margin:0;font-family:Arial;text-align:center;background:white;}
.top {background:#dc2626;color:white;padding:12px;font-size:22px;}
.number {font-size:160px;color:#dc2626;text-shadow:4px 4px black;}
.desk {font-size:50px;margin-bottom:20px;}
.panel {position:fixed;right:0;top:60px;width:260px;background:#f3f4f6;padding:10px;}

.overlay {
position:fixed;top:0;left:0;width:100%;height:100%;
background:black;color:white;display:flex;
justify-content:center;align-items:center;
font-size:28px;z-index:9999;
cursor:pointer;
}
</style>
</head>

<body>

<div class="overlay" id="unlock">TAP ANYWHERE TO ENABLE SOUND 🔊</div>

<div class="top" id="announcement"></div>
<div class="number" id="number">001</div>
<div class="desk" id="desk">Desk 1</div>
<div class="panel" id="panel"></div>

<audio id="ding" src="/sound" preload="auto"></audio>
<audio id="voice" preload="auto"></audio>

<script>
let unlocked = false;
let lastCallId = -1;

// 🔓 Unlock audio PROPERLY
document.getElementById("unlock").addEventListener("click", async () => {
    const ding = document.getElementById("ding");

    try {
        await ding.play();
        ding.pause();
        ding.currentTime = 0;

        unlocked = true;
        document.getElementById("unlock").style.display = "none";
        console.log("🔊 Audio unlocked");
    } catch (e) {
        alert("Tap again to enable sound");
    }
});

// 🔊 FORCE PLAY FUNCTION (retry system)
async function playAudio(audio){
    try{
        await audio.play();
    }catch(e){
        setTimeout(async ()=>{
            try{ await audio.play(); }catch(e){}
        },300);
    }
}

// 🔁 POLLING
setInterval(()=>{
fetch("/data").then(r=>r.json()).then(async data=>{

    document.getElementById("announcement").innerText = data.announcement;

    document.getElementById("panel").innerHTML =
        Object.entries(data.desks).map(
            ([k,v]) => `<div>${k}: ${v}</div>`
        ).join("");

    if(data.call_id !== lastCallId){

        document.getElementById("number").innerText = data.number;
        document.getElementById("desk").innerText = data.desk;

        if(unlocked){

            let ding = document.getElementById("ding");
            let voice = document.getElementById("voice");

            ding.currentTime = 0;
            await playAudio(ding);

            // wait 2 seconds
            setTimeout(async ()=>{
                voice.src = "/voice/" + data.number + "/" + data.desk + "?t=" + Date.now();
                await playAudio(voice);
            },2000);
        }

        lastCallId = data.call_id;
    }

});
},1000);
</script>

</body>
</html>
""")

# ================= STAFF =================
@app.route("/staff", methods=["GET","POST"])
def staff():
    global current_number, announcement, call_id

    if request.method == "POST":
        action = request.form.get("action")
        desk = request.form.get("desk")

        if action == "next":
            num = str(current_number).zfill(3)
            desks[desk] = num
            last_called["number"] = num
            last_called["desk"] = desk
            current_number += 1
            call_id += 1

        elif action == "recall":
            num = desks.get(desk)
            if num != "---":
                last_called["number"] = num
                last_called["desk"] = desk
                call_id += 1

        elif action == "assign":
            num = request.form.get("num")
            if num and num.isdigit():
                num = str(int(num)).zfill(3)
                desks[desk] = num
                last_called["number"] = num
                last_called["desk"] = desk
                call_id += 1

        elif action == "announce":
            txt = request.form.get("text")
            if txt:
                announcement = txt

    return render_template_string("""
<html>
<body style="background:#0f172a;color:white;font-family:Arial;padding:20px;">

<h1>STAFF CONTROL</h1>

{% for d in desks %}
<div style="background:#1e293b;padding:10px;margin:10px;">
<b>{{d}} → {{desks[d]}}</b><br>
<form method="post">
<input type="hidden" name="desk" value="{{d}}">
<button name="action" value="next">NEXT</button>
<button name="action" value="recall">RECALL</button>
</form>
</div>
{% endfor %}

</body>
</html>
""", desks=desks)

# ================= DATA =================
@app.route("/data")
def data():
    return jsonify({
        "number": last_called["number"],
        "desk": last_called["desk"],
        "announcement": announcement,
        "desks": desks,
        "call_id": call_id
    })

# ================= AUDIO =================
@app.route("/voice/<num>/<desk>")
def voice(num, desk):
    return send_file(get_voice(num, desk))

@app.route("/sound")
def sound():
    return send_file("dingdong.wav")

# ================= RUN =================
if __name__ == "__main__":
    app.run()
