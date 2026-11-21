import time, sys
from hx711 import HX711

CHIP = int(sys.argv[1]) if len(sys.argv) > 1 else 0
hx = HX711(5, 6, CHIP)

print("Warming up for 20 s - keep your hands off the load cell...")
t0 = time.time()
while time.time() - t0 < 20:
    try:
        hx.read_raw()
    except RuntimeError:
        pass
base = hx.read_avg(15)
print(f"Baseline: {base:.0f}. Now press and release the free end. Ctrl+C to stop.\n")
try:
    while True:
        try:
            raw = hx.read_avg(5)
        except RuntimeError as e:
            print("  ", e); time.sleep(0.5); continue
        d = raw - base
        bar = "#" * min(40, int(abs(d) / 2000))
        print(f"raw {raw:>10.0f}   change {d:>+9.0f}  {bar}")
except KeyboardInterrupt:
    hx.close()
