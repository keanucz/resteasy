// Pillow sensors on the Arduino Uno R3: the head-on-pillow switch plate (coord/CONTRACT.md 1).
//
// The plate is two cardboard sheets faced with aluminium foil; a head pressing them together
// closes the circuit. Wiring:
//   plate side 1 -> pin 2 (INPUT_PULLUP, so pressed reads LOW)
//   plate side 2 -> GND
//   LED on pin 13 through 1 kOhm (mirrors the contact: on = head on the pillow)
//   pin 1 (TX) -> 1 kOhm -> Waveshare GPIO44, with 2 kOhm from GPIO44 to GND; Uno GND -> Waveshare GND
//     (the voice unit in the pillow forwards every line as "UNO <line>"; firmware/README.md "The Uno")
//
// Output: one JSON object per line at 9600 baud (UNO_BAUD in voice_unit.ino), every 500 ms and at
// once when the contact changes. Only the fields this board has; the rest are null as the contract
// asks. Under 200 chars (the voice unit drops longer lines). The Uno does NOT decide what a reading
// means: lay_down (5 s), bed_exit (30 s) and the sleep rules are derived on the server
// (backend/app/agents/night_watch.py, sleep_events.py). Only a short electrical debounce lives here.
//
//   {"head_on":1,"motion":null,"room_motion":null,"light":null,"temp_c":null,"humidity":null,"fine":0,"talk":0,"family":0}

const int PLATE_PIN = 2;
const int LED_PIN = 13;

const unsigned long DEBOUNCE_MS = 150;   // foil contact bounce and a head shifting; meaning is the server's
const unsigned long REPORT_MS = 500;     // the contract's ~2 reports per second
const unsigned long BAUD = 9600;

bool headOn = false;        // debounced contact
bool rawState = false;
unsigned long rawSince = 0;
unsigned long lastReport = 0;

void report() {
  Serial.print(F("{\"head_on\":"));
  Serial.print(headOn ? 1 : 0);
  Serial.print(F(",\"motion\":null,\"room_motion\":null,\"light\":null,\"temp_c\":null,\"humidity\":null"));
  Serial.println(F(",\"fine\":0,\"talk\":0,\"family\":0}"));
}

void setup() {
  Serial.begin(BAUD);
  pinMode(PLATE_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.println(F("{\"boot\":\"pillow_uno\",\"plate_pin\":2}"));
}

void loop() {
  bool pressed = digitalRead(PLATE_PIN) == LOW;
  unsigned long now = millis();

  if (pressed != rawState) {
    rawState = pressed;
    rawSince = now;
  }
  if (rawState != headOn && now - rawSince >= DEBOUNCE_MS) {
    headOn = rawState;
    digitalWrite(LED_PIN, headOn ? HIGH : LOW);
    report();                 // on change: don't make the server wait for the next tick
    lastReport = now;
  }
  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    report();
  }
  delay(10);
}
