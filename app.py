from flask import Flask, request, jsonify, send_file
from flask import render_template_string
from gtts import gTTS
import os

app = Flask(__name__)

# ========= DATA =========
current_number = 1
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY"

DESKS = [f"Desk {i}" for i in range(1, 8)]
desks = {d: "---" for d in DESKS}

last_called = {"number": "001", "desk": "WELCOME"}

os.makedirs("voices", exist_ok=True)

# ========= VOICE =========
def get_voice(num, desk):
    filename = f"voices/{num}_{desk}.mp3"

    if not os.path.exists(filename):
        text = f"Number {int(num)}, please go to {desk}"
        tts = gTTS(text=text, lang="en")
        tts.save(filename)

    return filename

# ========= DISPLAY =========
@app.route("/")
def display():
    return render_template_string("""
<html>
<head>
<title>DISPLAY</title>
<style>
body {margin:0;text-align:center;font-family:Arial;}
.top {background:red;color:white;padding:10px;font-size:20px;}
.number {font-size:150px;color:red;text-shadow:3px 3px black;}
.desk {font-size:50px;}
.panel {position:fixed;right:0;top:60px;width:250px;background:#eee;padding:10px;}
</style>
</head>

<body>

<div class="top" id="announcement"></div>

<div class="number" id="number">001</div>
<div class="desk" id="desk">WELCOME</div>

<div class="panel" id="panel"></div>

<audio id="ding" src="/sound"></audio>
<audio id="voice"></audio>

<script>
let unlocked = false;
let last = "";

// unlock audio
document.body.onclick = function(){
    let d = document.getElementById("ding");
    d.play().then(()=>{
        d.pause();
        d.currentTime=0;
        unlocked = true;
    });
};

setInterval(()=>{
fetch("/data").then(r=>r.json()).then(data=>{

    document.getElementById("announcement").innerText = data.announcement;

    document.getElementById("panel").innerHTML =
        Object.entries(data.desks).map(
            ([k,v]) => k + ": " + v
        ).join("<br>");

    if(data.number !== last){

        document.getElementById("number").innerText = data.number;
        document.getElementById("desk").innerText = data.desk;

        if(unlocked){
            let ding = document.getElementById("ding");
            let voice = document.getElementById("voice");

            ding.play();

            setTimeout(()=>{
                voice.src = "/voice/" + data.number + "/" + data.desk;
                voice.play();
            },2000);
        }

        last = data.number;
    }

});
},1000);
</script>

</body>
</html>
""")

# ========= STAFF =========
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
            num = request.form.get("num")
            if num and num.isdigit():
                num = str(int(num)).zfill(3)
                desks[desk] = num
                last_called["number"] = num
                last_called["desk"] = f"GO TO {desk}"

        elif action == "announce":
            announcement = request.form.get("text")

    return render_template_string("""
<h1>STAFF CONTROL</h1>

{% for d in desks %}
<p>{{d}} → {{desks[d]}}</p>

<form method="post">
<input type="hidden" name="desk" value="{{d}}">
<button name="action" value="next">NEXT</button>
<button name="action" value="recall">RECALL</button>
</form>
{% endfor %}

<h3>Manual</h3>
<form method="post">
<input name="num">
<select name="desk">
{% for d in desks %}<option>{{d}}</option>{% endfor %}
</select>
<button name="action" value="assign">Assign</button>
</form>

<h3>Announcement</h3>
<form method="post">
<input name="text">
<button name="action" value="announce">Update</button>
</form>
""", desks=desks)

# ========= DATA =========
@app.route("/data")
def data():
    return jsonify({
        "number": last_called["number"],
        "desk": last_called["desk"],
        "announcement": announcement,
        "desks": desks
    })

# ========= AUDIO =========
@app.route("/voice/<num>/<desk>")
def voice(num, desk):
    return send_file(get_voice(num, desk))

@app.route("/sound")
def sound():
    return send_file("dingdong.wav")

# ========= RUN =========
if __name__ == "__main__":
    app.run()
