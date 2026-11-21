import threading, time, datetime, textwrap

from PIL import ImageFont

try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306      # use sh1106 if your OLED needs it
    HAVE_LUMA = True
except ImportError:
    HAVE_LUMA = False

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W = "white"


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


# ------------------------------------------------------------------
#  Little pixel-art helpers (drawn with shapes, so no image files)
# ------------------------------------------------------------------
def dog(d, x, y, mood="idle", t=0.0):
    """Dog head, 44 wide x 44 tall, top-left at (x, y).
    mood: idle | eat | happy | sad | sleep"""
    flap = 2 if (mood in ("happy", "eat") and int(t * 4) % 2) else 0
    # floppy ears (behind the head)
    d.ellipse((x, y + 6 - flap, x + 12, y + 28), fill=W)
    d.ellipse((x + 32, y + 6 - flap, x + 44, y + 28), fill=W)
    # head
    d.ellipse((x + 6, y + 4, x + 38, y + 36), fill=0, outline=W)

    ey = y + 17
    blink = (t % 4.0) < 0.3
    if mood == "happy":                               # ^ ^
        d.arc((x + 12, ey - 3, x + 20, ey + 4), 200, 340, fill=W)
        d.arc((x + 24, ey - 3, x + 32, ey + 4), 200, 340, fill=W)
    elif mood == "sleep" or (blink and mood != "sad"):  # - -
        d.line((x + 13, ey, x + 19, ey), fill=W)
        d.line((x + 25, ey, x + 31, ey), fill=W)
    elif mood == "sad":                               # worried brows + tear
        d.ellipse((x + 14, ey - 1, x + 18, ey + 3), fill=W)
        d.ellipse((x + 26, ey - 1, x + 30, ey + 3), fill=W)
        d.line((x + 11, ey - 3, x + 19, ey - 6), fill=W)
        d.line((x + 25, ey - 6, x + 33, ey - 3), fill=W)
        ty = ey + 4 + int((t * 6) % 9)
        d.ellipse((x + 31, ty, x + 33, ty + 2), fill=W)
    else:                                             # round eyes
        d.ellipse((x + 14, ey - 2, x + 18, ey + 2), fill=W)
        d.ellipse((x + 26, ey - 2, x + 30, ey + 2), fill=W)

    # nose
    d.ellipse((x + 19, y + 23, x + 25, y + 27), fill=W)

    # mouth
    if mood == "happy":
        d.ellipse((x + 17, y + 28, x + 27, y + 34), fill=0, outline=W)
        d.ellipse((x + 20, y + 31, x + 24, y + 35), fill=W)       # tongue
    elif mood == "eat":
        if int(t * 5) % 2:                                         # chomp
            d.ellipse((x + 17, y + 28, x + 27, y + 35), fill=0, outline=W)
        else:
            d.line((x + 17, y + 31, x + 27, y + 31), fill=W)
    elif mood == "sad":
        d.arc((x + 16, y + 30, x + 22, y + 35), 180, 360, fill=W)
        d.arc((x + 22, y + 30, x + 28, y + 35), 180, 360, fill=W)
    else:
        d.line((x + 22, y + 27, x + 22, y + 29), fill=W)
        d.arc((x + 16, y + 25, x + 22, y + 31), 0, 180, fill=W)
        d.arc((x + 22, y + 25, x + 28, y + 31), 0, 180, fill=W)

    # collar + tag
    d.line((x + 11, y + 38, x + 33, y + 38), fill=W)
    d.ellipse((x + 20, y + 38, x + 25, y + 43), fill=W)

    if mood == "sleep":                                # floating z z Z
        n = int(t * 1.5) % 4
        for i, (zx, zy, ch) in enumerate(((30, -7, "z"), (36, -13, "z"), (42, -18, "Z"))):
            if n > i:
                d.text((x + zx, y + zy), ch, fill=W)


def heart(d, x, y):
    d.ellipse((x, y, x + 3, y + 3), fill=W)
    d.ellipse((x + 3, y, x + 6, y + 3), fill=W)
    d.polygon([(x, y + 2), (x + 6, y + 2), (x + 3, y + 6)], fill=W)


def kibble(d, x, t, y0=0, y1=50):
    for i in range(3):
        y = y0 + ((t * 40 + i * 17) % (y1 - y0))
        xx = x + (i % 2) * 3
        d.ellipse((xx, y, xx + 2, y + 2), fill=W)


def bowl(d, x, y, frac):
    d.polygon([(x, y), (x + 42, y), (x + 36, y + 12), (x + 6, y + 12)], outline=W)
    h = int(9 * max(0.0, min(1.0, frac)))
    if h > 0:
        d.rectangle((x + 8, y + 11 - h, x + 34, y + 11), fill=W)


# ------------------------------------------------------------------
class StatusDisplay:
    def __init__(self, feeder, scheduler, address=0x3C):
        self.feeder, self.scheduler = feeder, scheduler
        self.device = None
        self.big, self.mid = _font(20), _font(14)
        self._contrast = None
        if HAVE_LUMA:
            try:
                self.device = ssd1306(i2c(port=1, address=address),
                                      width=128, height=64)
            except Exception as e:
                print("OLED not available:", e)
        if self.device:
            threading.Thread(target=self._loop, daemon=True).start()

    # ---------- helpers ----------
    def _next_short(self):
        nf = self.scheduler.next_feed()
        if not nf:
            return "No schedule"
        return nf.split(" (")[0].replace("Today", "Next").replace("Tomorrow", "Tmrw")

    # ---------- main loop ----------
    def _loop(self):
        while True:
            fast = True
            try:
                now = datetime.datetime.now()
                t = time.time()
                s = self.feeder.state
                sleeping = now.hour >= 22 or now.hour < 6

                recent = False
                if s.get("last_feed"):
                    try:
                        age = (now - datetime.datetime.strptime(
                            s["last_feed"], "%Y-%m-%d %H:%M:%S")).total_seconds()
                        recent = age < 8
                    except ValueError:
                        pass

                level = 8 if (sleeping and s["status"] == "Ready") else 200
                if level != self._contrast:           # dim at night (saves the OLED)
                    self.device.contrast(level)
                    self._contrast = level

                with canvas(self.device) as d:
                    if s["status"] == "Dispensing":
                        self._screen_feed(d, t, s)
                    elif s["status"] == "Error":
                        self._screen_error(d, t, s)
                    elif recent:
                        self._screen_happy(d, t, s)
                    else:
                        fast = False
                        self._screen_idle(d, t, now, s, sleeping)
            except Exception as e:
                print("OLED error:", e)
            time.sleep(0.12 if fast else 0.25)

    # ---------- screens ----------
    def _screen_idle(self, d, t, now, s, sleeping):
        dog(d, 2, 18, "sleep" if sleeping else "idle", t)
        colon = ":" if int(t) % 2 == 0 else " "
        d.text((52, 0), now.strftime(f"%H{colon}%M"), font=self.big, fill=W)
        d.text((54, 27), now.strftime("%a %d %b"), fill=W)
        d.text((54, 39), "Sleeping" if sleeping and s["status"] == "Ready"
               else s["status"], fill=W)
        d.text((54, 51), self._next_short(), fill=W)

    def _screen_feed(self, d, t, s):
        poured, target = s.get("poured", 0.0), s.get("target", 0.0)
        est = s.get("estimated", False)
        frac = max(0.0, min(1.0, poured / target)) if target else 0.0
        dog(d, 0, 2, "eat", t)
        bowl(d, 2, 50, frac)
        kibble(d, 48, t)
        d.text((54, 0), "FEEDING", fill=W)
        num = f"{'~' if est else ''}{poured:.0f}"
        d.text((54, 11), num, font=self.big, fill=W)
        try:
            nw = int(d.textlength(num, font=self.big))
        except Exception:
            nw = 40
        d.text((54 + nw + 2, 20), "g", fill=W)
        d.text((54, 35), f"of {target:.0f}g", fill=W)
        d.rectangle((54, 50, 125, 61), outline=W)
        d.rectangle((56, 52, 56 + int(67 * frac), 59), fill=W)

    def _screen_happy(self, d, t, s):
        for i, hx in enumerate((8, 22, 36)):
            hy = 12 - int((t * 8 + i * 5) % 13)
            heart(d, hx, max(0, hy + 1))
        dog(d, 2, 18, "happy", t)
        d.text((52, 0), "Yum!", font=self.big, fill=W)
        amt = s.get("last_amount")
        d.text((54, 27), f"{amt:.0f}g fed" if amt is not None else "Fed!", fill=W)
        d.text((54, 39), self._next_short(), fill=W)
        d.text((54, 51), "Good dog!", fill=W)

    def _screen_error(self, d, t, s):
        dog(d, 2, 18, "sad", t)
        d.text((52, 0), "Oops!", font=self.big, fill=W)
        for i, line in enumerate(textwrap.wrap(s.get("message", ""), 12)[:3]):
            d.text((54, 27 + 12 * i), line, fill=W)
