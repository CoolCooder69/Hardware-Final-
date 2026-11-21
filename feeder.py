import json, os, time, threading, datetime
from gpiozero import AngularServo
from hx711 import HX711

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE, "config.json")))
LOG_FILE = os.path.join(BASE, "feed_log.jsonl")
CAL_FILE = os.path.join(BASE, "calibration.json")


class Feeder:
    def __init__(self):
        # Weighed mode needs a calibration file; otherwise use timed mode
        self.scale = None
        if os.path.exists(CAL_FILE):
            self.scale = HX711(CFG["hx_dt"], CFG["hx_sck"], CFG["gpio_chip"])
            self.scale.scale = json.load(open(CAL_FILE))["scale"]
        self.mode = "weighed" if self.scale else "timed"

        self.servo = AngularServo(
            CFG["servo_pin"], initial_angle=CFG["closed_angle"],
            min_angle=0, max_angle=180,
            min_pulse_width=0.0005, max_pulse_width=0.0025)
        time.sleep(0.6)
        self.servo.detach()          # stops jitter when idle

        self._lock = threading.Lock()
        self.state = {"status": "Ready", "message": f"Mode: {self.mode}",
                      "mode": self.mode,
                      "poured": 0.0, "target": 0.0, "estimated": False,
                      "last_feed": None, "last_amount": None}

    # ---------- public ----------
    def feed(self, grams, source="manual"):
        """Start a feeding in the background. Returns (ok, message)."""
        grams = float(grams)
        if not 5 <= grams <= CFG["max_portion"]:
            return False, f"Portion must be 5-{CFG['max_portion']} g"
        if not self._lock.acquire(blocking=False):
            return False, "Feeder is busy"
        threading.Thread(target=self._run, args=(grams, source),
                         daemon=True).start()
        return True, f"Feeding {grams:.0f} g started"

    def history(self, n=20):
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE) as f:
            lines = f.readlines()[-n:]
        return [json.loads(l) for l in reversed(lines)]

    # ---------- internal ----------
    def _set(self, status, message=""):
        self.state["status"] = status
        self.state["message"] = message

    def _dispense_timed(self, target):
        """No scale: run the gate open for a calculated time."""
        secs = min(target / CFG["fallback_g_per_s"], CFG["timeout_s"])
        self.state["estimated"] = True
        self.servo.angle = CFG["open_angle"]
        t0 = time.time()
        while time.time() - t0 < secs:
            self.state["poured"] = min(
                target, (time.time() - t0) * CFG["fallback_g_per_s"])
            self.state["message"] = f"Timed: {secs - (time.time() - t0):.0f}s left"
            time.sleep(0.1)
        return "ok_timed", target          # estimated amount

    def _dispense_weighed(self, target):
        """Scale present: stop when the target weight is reached."""
        self.state["estimated"] = False
        self.scale.tare()
        self.servo.angle = CFG["open_angle"]
        start = last_move = time.time()
        best = 0.0
        result = "ok"
        while True:
            w = self.scale.grams(n=3)
            self.state["poured"] = max(0.0, w)        # live reading for OLED/web
            self.state["message"] = f"{max(0.0, w):.0f} / {target:.0f} g"
            if w >= target - CFG["lead_grams"]:
                break
            now = time.time()
            if w > best + 1.0:
                best, last_move = w, now
            if now - last_move > CFG["no_flow_s"]:
                result = "no_flow"          # hopper empty or jammed
                break
            if now - start > CFG["timeout_s"]:
                result = "timeout"
                break
        return result, None

    def _run(self, target, source):
        result, final = "ok", 0.0
        try:
            self.state["target"] = target
            self.state["poured"] = 0.0
            self._set("Dispensing", f"Target {target:.0f} g")
            if self.scale is None:
                result, final = self._dispense_timed(target)
            else:
                result, _ = self._dispense_weighed(target)
        except Exception as e:
            result = f"error: {e}"
        finally:
            self.servo.angle = CFG["closed_angle"]
            time.sleep(0.7)
            self.servo.detach()
            if self.scale is not None:
                try:
                    # keep updating the live value while food settles
                    t0 = time.time()
                    while time.time() - t0 < 1.0:
                        self.state["poured"] = max(0.0, self.scale.grams(n=3))
                    final = self.scale.grams(n=10)
                except Exception:
                    pass
            self.state["poured"] = max(0.0, final)
            self._finish(source, target, final, result)
            self._lock.release()

    def _finish(self, source, target, final, result):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"time": now, "source": source, "target_g": target,
                 "actual_g": round(final, 1), "result": result,
                 "mode": self.mode}
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self.state["last_feed"] = now
        self.state["last_amount"] = round(final, 1)
        if result.startswith("ok"):
            note = " (estimated)" if result == "ok_timed" else ""
            self._set("Ready", f"Dispensed {final:.0f} g{note}")
        else:
            self._set("Error", f"{result} ({final:.0f} g dispensed)")
