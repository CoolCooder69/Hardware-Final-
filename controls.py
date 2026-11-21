import threading, time
from gpiozero import Button, OutputDevice, PWMOutputDevice
from feeder import CFG

BUTTON_PIN = 17
BUZZER_PIN = 27
BUZZER_PASSIVE = False             # True if the buzzer only sounds with a tone signal
BUZZER_ACTIVE_HIGH = True          # active buzzers only; False for low-trigger modules


class Controls:
    def __init__(self, feeder):
        self.feeder = feeder
        self.grams = CFG.get("button_portion", CFG["default_portion"])
        self.buzzer_on = CFG.get("buzzer_enabled", True)
        if BUZZER_PASSIVE:
            self.buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2500, initial_value=0)
        else:
            self.buzzer = OutputDevice(BUZZER_PIN, active_high=BUZZER_ACTIVE_HIGH,
                                       initial_value=False)
        self.button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
        self.button.when_pressed = self._pressed
        threading.Thread(target=self._buzz_loop, daemon=True).start()

    def _pressed(self):
        self.feeder.feed(self.grams, source="button")     # ignored if already busy

    def _on(self):
        if BUZZER_PASSIVE:
            self.buzzer.value = 0.5
        else:
            self.buzzer.on()

    def _beep(self, secs):
        if not self.buzzer_on:
            return
        self._on()
        time.sleep(secs)
        self.buzzer.off()

    def _dispensing(self):
        return self.feeder.state["status"] == "Dispensing"

    def _buzz_loop(self):
        last = self.feeder.state["status"]
        while True:
            try:
                status = self.feeder.state["status"]
                if status == "Dispensing":
                    self._beep(0.12)
                    time.sleep(0.12)
                    if self._dispensing():
                        self._beep(0.12)
                    time.sleep(0.5)
                else:
                    if last == "Dispensing":
                        if status == "Ready":
                            self._beep(0.6)                # done
                        elif status == "Error":
                            for _ in range(3):             # failed
                                self._beep(0.1); time.sleep(0.1)
                    time.sleep(0.05)
                last = status
            except Exception as e:
                print("Controls error:", e)
                self.buzzer.off()
                time.sleep(0.5)
