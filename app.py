from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

current_number = 1
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY •"

desks = {"Desk 1":"---","Desk 2":"---","Desk 3":"---","Desk 4":"---"}

last_called = {"number":"001","desk":"WELCOME"}

display_html = """
<!DOCTYPE html>
<html>
<head>
<title>DISPLAY</title>

<style>
body {margin:0;font-family:Arial;background:white;text-align:center;}
.top {background:red;color:white;padding:10px;font-size:20px;overflow:hidden;}
#scroll {white-space:nowrap;display:inline-block;animation:scroll 10s linear infinite;}
@keyframes scroll {from{transform:translateX(100%);} to{transform:translateX(-100%);}}
.number {font-size:150px;color:red;text-shadow:3px 3px black;}
.desk {font-size:50px;}
.logo {position:fixed;bottom:10px;left:10px;width:100px;}
</style>

</head>
<body>

<div class="top"><span id="scroll">{{announcement}}</span></div>
<div class="number" id="number">{{number}}</div>
<div class="desk" id="desk">{{desk}}</div>

<img src="/logo" class="logo">
<audio id="ding" src="/sound"></audio>

<script>
let lastNumber = "";
let unlocked = false;

// FORCE unlock
function unlock() {
    let audio = document.getElementById("ding");
    audio.play().then(()=>{
        audio.pause();
        audio.currentTime = 0;
        unlocked = true;
        console.log("Unlocked 🔊");
    }).catch(()=>{});
}

document.addEventListener("click", unlock);
setTimeout(unlock, 1500);

// SPEAK
function speak(text) {
    if (!unlocked) return;

    try {
        speechSynthesis.cancel();
        let msg = new SpeechSynthesisUtterance(text);
        msg.rate = 0.9;
        msg.pitch = 1;

        let voices = speechSynthesis.getVoices();
        msg.voice = voices.find(v=>v.name.toLowerCase().includes("female")) || voices[0];

        speechSynthesis.speak(msg);
    } catch(e){
        console.log("Voice failed");
    }
}

// LOOP
setInterval(()=>{
    fetch("/data")
    .then(r=>r.json())
    .then(data=>{
        if(data.number !== lastNumber){

            document.getElementById("number").innerText = data.number;
            document.getElementById("desk").innerText = data.desk;
            document.getElementById("scroll").innerText = data.announcement;

            let ding = document.getElementById("ding");

            if(unlocked){
                ding.currentTime = 0;
                ding.play().catch(()=>{});
            }

            setTimeout(()=>{
                speak("Number " + data.number + ". " + data.desk);
            },2000);

            lastNumber = data.number;
        }
    });
},1000);
</script>

</body>
</html>
"""

staff_html = """
<!DOCTYPE html>
<html>
<head>
<title>STAFF</title>
<style>
body{background:#0f172a;color:white;text-align:center;font-family:Arial;}
button{padding:10px;margin:5px;font-size:16px;}
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

<form method="post">
<input name="manual_number" placeholder="Number">
<select name="desk">
{% for desk in desks %}
<option>{{desk}}</option>
{% endfor %}
</select>
<button name="action" value="assign">ASSIGN</button>
</form>

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(display_html, **last_called, announcement=announcement)

@app.route("/staff", methods=["GET","POST"])
def staff():
    global current_number

    if request.method=="POST":
        action = request.form.get("action")
        desk = request.form.get("desk")

        if action=="next":
            num = str(current_number).zfill(3)
            desks[desk]=num
            last_called["number"]=num
            last_called["desk"]=f"GO TO {desk}"
            current_number+=1

        elif action=="recall":
            num = desks.get(desk)
            if num!="---":
                last_called["number"]=num
                last_called["desk"]=f"GO TO {desk}"

        elif action=="assign":
            num = request.form.get("manual_number")
            if num and num.isdigit():
                num = str(int(num)).zfill(3)
                desks[desk]=num
                last_called["number"]=num
                last_called["desk"]=f"GO TO {desk}"

    return render_template_string(staff_html, desks=desks)

@app.route("/data")
def data():
    return jsonify({**last_called,"announcement":announcement})

@app.route("/sound")
def sound():
    return send_file("dingdong.wav")

@app.route("/logo")
def logo():
    return send_file("logo.gif")

if __name__ == "__main__":
    app.run()
