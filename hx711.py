import lgpio, time, statistics

BAD = {-8388608, 8388607, 0}     # saturated / powered-down / empty reads

class HX711:
    def __init__(self, dt=5, sck=6, chip=0):
        self.dt, self.sck = dt, sck
        self.h = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_input(self.h, dt)
        lgpio.gpio_claim_output(self.h, sck, 0)
        self.offset = 0.0
        self.scale = 1.0          # raw counts per gram
        self.reset()

    def reset(self):
        # SCK high >60us powers the chip down; low powers it back up
        lgpio.gpio_write(self.h, self.sck, 1)
        time.sleep(0.1)
        lgpio.gpio_write(self.h, self.sck, 0)
        time.sleep(0.5)

    def _wait_ready(self, timeout=1.0):
        t0 = time.time()
        while lgpio.gpio_read(self.h, self.dt):
            if time.time() - t0 > timeout:
                raise RuntimeError("HX711 not ready - check wiring/power")
            time.sleep(0.001)

    def _read_once(self):
        self._wait_ready()
        val = 0
        for _ in range(24):
            lgpio.gpio_write(self.h, self.sck, 1)
            val = (val << 1) | lgpio.gpio_read(self.h, self.dt)
            lgpio.gpio_write(self.h, self.sck, 0)
        # 25th pulse = channel A, gain 128 for next reading
        lgpio.gpio_write(self.h, self.sck, 1)
        lgpio.gpio_write(self.h, self.sck, 0)
        if val & 0x800000:
            val -= 1 << 24
        return val

    def read_raw(self):
        """One valid reading; glitches (power-down, saturation) are discarded."""
        for _ in range(6):
            try:
                v = self._read_once()
            except RuntimeError:
                self.reset()
                continue
            if v not in BAD:
                return v
            time.sleep(0.05)
        raise RuntimeError("HX711 returns only invalid readings - check load cell wiring")

    def read_avg(self, n=10):
        # median rejects any remaining outliers
        return statistics.median(self.read_raw() for _ in range(n))

    def tare(self, n=15):
        self.offset = self.read_avg(n)

    def grams(self, n=5):
        return (self.read_avg(n) - self.offset) / self.scale

    def close(self):
        lgpio.gpio_write(self.h, self.sck, 0)   # leave SCK low on exit
        lgpio.gpiochip_close(self.h)
