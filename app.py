from flask import Flask, render_template_string, request, jsonify, send_file
from gtts import gTTS
import os

app = Flask(__name__)

# ================= CONFIG =================
current_number = 1
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY •"

DESKS = [f"Desk {i}" for i in range(1, 8)]
desks = {d: "---" for d in DESKS}

last_called = {"number": "001", "desk": "WELCOME"}

VOICE_FOLDER = "voices"
os.makedirs(VOICE_FOLDER, exist_ok=True)

# ================= VOICE =================
def generate_voice(number, desk):
    filename = f"{VOICE_FOLDER}/{number}_{desk}.mp3"

    if not os.path.exists(filename):
        text = f"Number {int(number)}, please go to {desk}"
        tts = gTTS(text=text, lang='en')
        tts.save(filename)

    return filename

# ================= DISPLAY =================
display_html = """
<!DOCTYPE html>
<html>
<head>
<title>DISPLAY</title>

<style>
body {margin:0;font-family:Arial;background:white;text-align:center;}
.top {background:red;color:white;padding:12px;font-size:22px;overflow:hidden;}
#scroll {white-space:nowrap;display:inline-block;animation:scroll 12s linear infinite;}
@keyframes scroll {from{transform:translateX(100%);} to{transform:translateX(-100%);}}

.number {font-size:160px;color:red;text-shadow:4px 4px black;}
.desk {font-size:55px;margin-bottom:10px;}

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

<div class="overlay" id="unlock">TAP SCREEN TO ENABLE SOUND 🔊</div>

<div class="top"><span id="scroll">{{announcement}}</span></div>

<div class="number" id="number">{{number}}</div>
<div class="desk" id="desk">{{desk}}</div>

<div class="panel" id="panel"></div>

<audio id="ding" src="/sound"></audio>
<audio id="voice"></audio>

<script>
let unlocked = false;
let lastNumber = "";

// 🔊 AUDIO UNLOCK
document.body.addEventListener("click", function unlock(){
    let ding = document.getElementById("ding");
    ding.play().then(()=>{
        ding.pause();
        ding.currentTime = 0;
        unlocked = true;
        document.getElementById("unlock").style.display="none";
        document.body.removeEventListener("click", unlock);
    }).catch(()=>{});
});

// 🔁 LOOP
setInterval(()=>{
fetch("/data")
.then(r=>r.json())
.then(data=>{

    document.getElementById("panel").innerHTML =
        Object.entries(data.desks).map(
            ([k,v]) => `<div class="row">${k} <span>${v}</span></div>`
        ).join("");

    if(data.number !== lastNumber){

        document.getElementById("number").innerText = data.number;
        document.getElementById("desk").innerText = data.desk;
        document.getElementById("scroll").innerText = data.announcement;

        if(unlocked){
            let ding = document.getElementById("ding");
            let voice = document.getElementById("voice");

            ding.currentTime = 0;
            ding.play().catch(()=>{});

            setTimeout(()=>{
                voice.src = "/voice/" + data.number + "/" + data.desk;
                voice.play().catch(()=>{});
            },2000);
        }

        lastNumber = data.number;
    }

});
},1000);
</script>

</body>
</html>
"""

# ================= STAFF =================
staff_html = """
<!DOCTYPE html>
<html>
<head>
<title>STAFF CONTROL</title>
<style>
body{background:#0f172a;color:white;text-align:center;font-family:Arial;}
button{padding:10px;margin:5px;font-size:16px;}
input,select{padding:8px;margin:5px;}
</style>
</head>
<body>

<h1>STAFF CONTROL</h1>

{% for desk in desks %}
<h2>{{desk}} → {{desks[desk]}}</h2>
<form method="post">
<input type="hidden" name="desk" value="{{desk}}">
<button name="action" value="next">NEXT</button>
<button name="action" value="recall">RECALL</button>
</form>
{% endfor %}

<h2>Manual Assign</h2>
<form method="post">
<input name="manual_number" placeholder="Enter number">
<select name="desk">
{% for desk in desks %}
<option>{{desk}}</option>
{% endfor %}
</select>
<button name="action" value="assign">ASSIGN</button>
</form>

<h2>Update Announcement</h2>
<form method="post">
<input name="announcement" placeholder="New announcement">
<button name="action" value="update_announcement">UPDATE</button>
</form>

</body>
</html>
"""

# ================= ROUTES =================
@app.route("/")
def home():
    return render_template_string(display_html,
        number=last_called["number"],
        desk=last_called["desk"],
        announcement=announcement
    )

@app.route("/staff", methods=["GET","POST"])
def staff():
    global current_number, announcement

    if request.method == "POST":
        action = request.form.get("action")
        desk = request.form.get("desk")

        if action == "next":
            num = str(current_number).zfill(3)
            desks[desk] = num
            last_called["number"] = num
            last_called["desk"] = f"GO TO {desk}"
            current_number += 1

        elif action == "recall":
            num = desks.get(desk)
            if num != "---":
                last_called["number"] = num
                last_called["desk"] = f"GO TO {desk}"

        elif action == "assign":
            num = request.form.get("manual_number")
            if num and num.isdigit():
                num = str(int(num)).zfill(3)
                desks[desk] = num
                last_called["number"] = num
                last_called["desk"] = f"GO TO {desk}"

        elif action == "update_announcement":
            new_text = request.form.get("announcement")
            if new_text:
                announcement = new_text

    return render_template_string(staff_html, desks=desks)

@app.route("/data")
def data():
    return jsonify({
        "number": last_called["number"],
        "desk": last_called["desk"],
        "announcement": announcement,
        "desks": desks
    })

@app.route("/voice/<num>/<desk>")
def voice(num, desk):
    return send_file(generate_voice(num, desk))

@app.route("/sound")
def sound():
    return send_file("dingdong.wav")

# ================= RUN =================
if __name__ == "__main__":
    app.run()
