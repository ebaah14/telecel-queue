from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

# ================= DATA =================
current_number = 1
announcement = "WELCOME TO TELECEL • PLEASE HAVE YOUR ID READY •"

desks = {
    "Desk 1": "---",
    "Desk 2": "---",
    "Desk 3": "---",
    "Desk 4": "---"
}

last_called = {"number": "001", "desk": "WELCOME"}

# ================= DISPLAY =================
display_html = """
<!DOCTYPE html>
<html>
<head>
<title>DISPLAY</title>

<style>
body { margin:0; font-family:Arial; background:white; text-align:center; }

.top {
    background:red;
    color:white;
    padding:10px;
    font-size:20px;
    overflow:hidden;
    white-space:nowrap;
}

#scroll {
    display:inline-block;
    padding-left:100%;
    animation:scroll 12s linear infinite;
}

@keyframes scroll {
    from {transform:translateX(0);}
    to {transform:translateX(-100%);}
}

.number {
    font-size:150px;
    color:red;
    text-shadow: 3px 3px black;
}

.desk {
    font-size:50px;
}

.logo {
    position:fixed;
    bottom:10px;
    left:10px;
    width:110px;
}
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
let audioUnlocked = false;

// Unlock audio on first tap
document.addEventListener("click", () => {
    audioUnlocked = true;

    let ding = document.getElementById("ding");
    ding.play().then(() => {
        ding.pause();
        ding.currentTime = 0;
    }).catch(() => {});
});

// Get female voice
function getFemaleVoice() {
    let voices = speechSynthesis.getVoices();
    return voices.find(v =>
        v.name.toLowerCase().includes("female") ||
        v.name.toLowerCase().includes("zira") ||
        v.name.toLowerCase().includes("google uk english female")
    ) || voices[0];
}

// Speak safely
function speak(text) {
    if (!audioUnlocked) return;

    speechSynthesis.cancel();

    let speech = new SpeechSynthesisUtterance(text);
    speech.voice = getFemaleVoice();
    speech.rate = 0.9;
    speech.pitch = 1;

    speechSynthesis.speak(speech);
}

// Ensure voices load
speechSynthesis.onvoiceschanged = () => {};

// Main loop
setInterval(() => {
    fetch('/data')
    .then(res => res.json())
    .then(data => {

        if (data.number !== lastNumber) {

            document.getElementById("number").innerText = data.number;
            document.getElementById("desk").innerText = data.desk;
            document.getElementById("scroll").innerText = data.announcement;

            let ding = document.getElementById("ding");

            if (audioUnlocked) {
                ding.currentTime = 0;
                ding.play();
            }

            setTimeout(() => {
                speak("Number " + data.number + ". " + data.desk);
            }, 2000);

            lastNumber = data.number;
        }
    });
}, 1000);
</script>

</body>
</html>
"""

# ================= STAFF =================
staff_html = """
<!DOCTYPE html>
<html>
<head>
<title>STAFF</title>

<style>
body { font-family:Arial; background:#0f172a; color:white; text-align:center; }

button {
    font-size:18px;
    padding:10px 20px;
    margin:5px;
    border:none;
    cursor:pointer;
}

.next { background:green; }
.recall { background:blue; }
.assign { background:orange; }

input, select {
    padding:8px;
    font-size:16px;
    margin:5px;
}
</style>

</head>
<body>

<h1>STAFF CONTROL</h1>

{% for desk in desks %}
<div>
    <h2>{{desk}} → {{desks[desk]}}</h2>
    <form method="post">
        <input type="hidden" name="desk" value="{{desk}}">
        <button class="next" name="action" value="next">NEXT</button>
        <button class="recall" name="action" value="recall">RECALL</button>
    </form>
</div>
{% endfor %}

<h2>Manual Assign</h2>
<form method="post">
    <input name="manual_number" placeholder="Enter number">
    <select name="desk">
        {% for desk in desks %}
        <option value="{{desk}}">{{desk}}</option>
        {% endfor %}
    </select>
    <button class="assign" name="action" value="assign">ASSIGN</button>
</form>

<h2>Announcement</h2>
<form method="post">
    <input name="announcement" placeholder="New announcement">
    <button name="action" value="update_announcement">UPDATE</button>
</form>

</body>
</html>
"""

# ================= ROUTES =================
@app.route("/display")
def display():
    return render_template_string(display_html,
                                  number=last_called["number"],
                                  desk=last_called["desk"],
                                  announcement=announcement)

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
            if num and num != "---":
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
        "announcement": announcement
    })

@app.route("/sound")
def sound():
    return send_file("dingdong.wav")

@app.route("/logo")
def logo():
    return send_file("logo.gif")

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
