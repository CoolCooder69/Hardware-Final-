import json, os, threading, time, uuid, datetime
from feeder import CFG

BASE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(BASE, "schedule.json")


class Scheduler:
    def __init__(self, feeder):
        self.feeder = feeder
        self._lock = threading.Lock()
        self._fired = {}                  # schedule id -> date it last fired
        self.items = self._load()
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------- storage ----------
    def _load(self):
        try:
            with open(FILE) as f:
                return json.load(f)["schedules"]
        except Exception:
            items = [self._make("07:00", CFG["default_portion"]),
                     self._make("18:00", CFG["default_portion"])]
            self._save(items)
            return items

    @staticmethod
    def _make(hhmm, grams):
        return {"id": uuid.uuid4().hex[:8], "time": hhmm,
                "grams": float(grams), "enabled": True}

    def _save(self, items):
        tmp = FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"schedules": items}, f, indent=2)
        os.replace(tmp, FILE)             # atomic: no half-written file

    # ---------- public ----------
    def list(self):
        with self._lock:
            return sorted(self.items, key=lambda s: s["time"])

    def add(self, hhmm, grams):
        datetime.datetime.strptime(hhmm, "%H:%M")        # raises if invalid
        grams = float(grams)
        if not 5 <= grams <= CFG["max_portion"]:
            raise ValueError(f"Portion must be 5-{CFG['max_portion']} g")
        with self._lock:
            item = self._make(hhmm, grams)
            self.items.append(item)
            self._save(self.items)
        return item

    def remove(self, sid):
        with self._lock:
            n = len(self.items)
            self.items = [s for s in self.items if s["id"] != sid]
            self._save(self.items)
            return len(self.items) < n

    def set_enabled(self, sid, enabled):
        with self._lock:
            for s in self.items:
                if s["id"] == sid:
                    s["enabled"] = bool(enabled)
                    self._save(self.items)
                    return True
        return False

    def next_feed(self):
        now = datetime.datetime.now()
        best = None
        with self._lock:
            for s in self.items:
                if not s["enabled"]:
                    continue
                h, m = map(int, s["time"].split(":"))
                t = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if t <= now:
                    t += datetime.timedelta(days=1)
                if best is None or t < best[0]:
                    best = (t, s["grams"])
        if not best:
            return None
        day = "Today" if best[0].date() == now.date() else "Tomorrow"
        return f"{day} {best[0].strftime('%H:%M')} ({best[1]:.0f} g)"

    # ---------- background loop ----------
    def _loop(self):
        while True:
            now = datetime.datetime.now()
            today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
            with self._lock:
                due = [s for s in self.items if s["enabled"]
                       and s["time"] == hhmm and self._fired.get(s["id"]) != today]
            for s in due:
                ok, msg = self.feeder.feed(s["grams"], source="schedule")
                # if only busy, retry on the next tick within this minute
                if ok or msg != "Feeder is busy":
                    self._fired[s["id"]] = today
            time.sleep(5)
