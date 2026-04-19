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
call_id = 0  # 🔥 NEW: triggers recall updates

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
.row {display:flex;justify-content:space-between;margin:6px 0;font-weight:bold;}

.overlay {
position:fixed;top:0;left:0;width:100%;height:100%;
background:black;color:white;display:flex;
justify-content:center;align-items:center;
font-size:28px;z-index:9999;
}
</style>
</head>

<body>

<div class="overlay" id="unlock">TAP TO ENABLE SOUND 🔊</div>

<div class="top" id="announcement"></div>

<div class="number" id="number">001</div>
<div class="desk" id="desk">Desk 1</div>

<div class="panel" id="panel"></div>

<audio id="ding" src="/sound"></audio>
<audio id="voice"></audio>

<script>
let unlocked = false;
let lastCallId = -1;

// 🔓 unlock audio
document.body.addEventListener("click", async function(){
    if(!unlocked){
        let d = document.getElementById("ding");
        try{
            await d.play();
            d.pause();
            d.currentTime = 0;
            unlocked = true;
            document.getElementById("unlock").style.display="none";
        }catch(e){}
    }
});

// 🔄 polling
setInterval(()=>{
fetch("/data").then(r=>r.json()).then(async data=>{

    document.getElementById("announcement").innerText = data.announcement;

    document.getElementById("panel").innerHTML =
        Object.entries(data.desks).map(
            ([k,v]) => `<div class="row">${k} <span>${v}</span></div>`
        ).join("");

    // 🔥 FIX: use call_id instead of number
    if(data.call_id !== lastCallId){

        document.getElementById("number").innerText = data.number;
        document.getElementById("desk").innerText = data.desk;

        if(unlocked){
            let ding = document.getElementById("ding");
            let voice = document.getElementById("voice");

            try{
                ding.currentTime = 0;
                await ding.play();
            }catch(e){}

            setTimeout(async ()=>{
                try{
                    voice.src = "/voice/" + data.number + "/" + data.desk;
                    await voice.play();
                }catch(e){}
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
            call_id += 1  # 🔥 trigger

        elif action == "recall":
            num = desks.get(desk)
            if num != "---":
                last_called["number"] = num
                last_called["desk"] = desk
                call_id += 1  # 🔥 trigger recall

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
<head>
<style>
body{background:#0f172a;color:white;font-family:Arial;padding:20px;}
.card{background:#1e293b;padding:15px;margin:10px;border-radius:10px;}
button{padding:10px;margin:5px;border:none;border-radius:6px;}
.next{background:#22c55e;}
.recall{background:#3b82f6;color:white;}
</style>
</head>
<body>

<h1>STAFF CONTROL</h1>

{% for d in desks %}
<div class="card">
<h3>{{d}} → {{desks[d]}}</h3>
<form method="post">
<input type="hidden" name="desk" value="{{d}}">
<button class="next" name="action" value="next">NEXT</button>
<button class="recall" name="action" value="recall">RECALL</button>
</form>
</div>
{% endfor %}

<div class="card">
<h3>Manual Assign</h3>
<form method="post">
<input name="num">
<select name="desk">
{% for d in desks %}<option>{{d}}</option>{% endfor %}
</select>
<button name="action" value="assign">Assign</button>
</form>
</div>

<div class="card">
<h3>Announcement</h3>
<form method="post">
<input name="text">
<button name="action" value="announce">Update</button>
</form>
</div>

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
        "call_id": call_id  # 🔥 important
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
