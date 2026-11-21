from flask import Flask, jsonify, request, render_template
from feeder import Feeder, CFG
from scheduler import Scheduler
from display import StatusDisplay
from controls import Controls
from auth import install as install_auth
import datetime

app = Flask(__name__)
install_auth(app)
feeder = Feeder()
scheduler = Scheduler(feeder)
StatusDisplay(feeder, scheduler)
Controls(feeder)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify(feeder.state | {
        "default_portion": CFG["default_portion"],
        "max_portion": CFG["max_portion"],
        "next_feed": scheduler.next_feed(),
        "now": datetime.datetime.now().strftime("%H:%M:%S"),
    })


@app.post("/api/feed")
def feed():
    data = request.get_json(silent=True) or {}
    grams = data.get("grams", CFG["default_portion"])
    try:
        ok, msg = feeder.feed(grams, source="manual")
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Invalid portion"), 400
    return jsonify(ok=ok, message=msg), (200 if ok else 409)


@app.get("/api/log")
def log():
    return jsonify(feeder.history())


@app.get("/api/schedule")
def get_schedule():
    return jsonify(scheduler.list())


@app.post("/api/schedule")
def add_schedule():
    data = request.get_json(silent=True) or {}
    try:
        item = scheduler.add(data.get("time", ""), data.get("grams"))
    except (TypeError, ValueError) as e:
        return jsonify(ok=False, message=str(e)), 400
    return jsonify(ok=True, item=item), 201


@app.delete("/api/schedule/<sid>")
def delete_schedule(sid):
    return jsonify(ok=scheduler.remove(sid))


@app.post("/api/schedule/<sid>/toggle")
def toggle_schedule(sid):
    data = request.get_json(silent=True) or {}
    return jsonify(ok=scheduler.set_enabled(sid, data.get("enabled", True)))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
