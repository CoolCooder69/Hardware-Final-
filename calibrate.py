import json, time, statistics
from hx711 import HX711

DT, SCK, CHIP = 5, 6, 0          # Pi 4 -> chip 0

def sample(hx, n=30):
    vals = []
    while len(vals) < n:
        try:
            vals.append(hx.read_raw())
        except RuntimeError:
            pass
    return statistics.mean(vals), statistics.pstdev(vals)

hx = HX711(DT, SCK, CHIP)

print("Warming up 20 s - keep hands off the load cell...")
t0 = time.time()
while time.time() - t0 < 20:
    try: hx.read_raw()
    except RuntimeError: pass

input("\nPut the EMPTY bowl on the scale, keep it still, press Enter...")
offset, noise = sample(hx)
print(f"Empty reading: {offset:.0f}  (noise +/- {noise:.0f})")

known = float(input("\nPlace a known weight on the bowl and type its weight in grams: "))
input("Wait until it is still, then press Enter...")
loaded, noise2 = sample(hx)
change = loaded - offset
print(f"Loaded reading: {loaded:.0f}  -> change {change:+.0f} counts")

if abs(change) < max(5 * max(noise, noise2), 2000):
    print("\nFAILED: the weight barely changed the reading.")
    print("The load cell signal is not reaching the HX711. Check:")
    print(" - E+/E- (red/black) and A+/A- (green/white) wires are firmly connected")
    print(" - the weight is on the FREE end of the cell, along its arrow")
    print("Nothing was saved.")
    hx.close()
    raise SystemExit(1)

scale = change / known
json.dump({"scale": scale}, open("calibration.json", "w"))
print(f"\nScale factor: {scale:.2f} counts/gram  -> saved calibration.json")

hx.offset, hx.scale = offset, scale
print("\nLive check (Ctrl+C to stop). Remove the weight: it should read ~0 g.")
try:
    while True:
        print(f"{hx.grams(n=5):7.1f} g")
        time.sleep(0.5)
except KeyboardInterrupt:
    hx.close()
