// The `buzz` command's sounds (coord/CONTRACT.md 3), shared by the boards that can make them:
//   chime  two soft rising notes, about 1 s: the gentle lead-in before a reminder is spoken
//   alert  three short beeps
// Text command (USB line, BLE CTRL write, or an ESP-NOW C packet): "BUZZ <chime|alert> <repeat 1-3>".
//
// The pillow node plays them on the kit's passive buzzer with Player (tone() per note); the voice
// unit renders the same notes as sine waves into its speaker stream.
#pragma once
#include <Arduino.h>

namespace buzz {

struct Note {
  uint16_t hz;  // 0 = silence
  uint16_t ms;
};

struct Pattern {
  const Note *notes;
  size_t count;
  bool bell;  // fade each note out like a bell (the speaker can; a passive buzzer just stops)
};

// C5 then G5, ringing out: 450 + 50 + 500 = 1000 ms
const Note CHIME_NOTES[] = {{523, 450}, {0, 50}, {784, 500}};
const Note ALERT_NOTES[] = {{1000, 150}, {0, 100}, {1000, 150}, {0, 100}, {1000, 150}};
const Pattern CHIME = {CHIME_NOTES, sizeof(CHIME_NOTES) / sizeof(Note), true};
const Pattern ALERT = {ALERT_NOTES, sizeof(ALERT_NOTES) / sizeof(Note), false};
const uint16_t REPEAT_GAP_MS = 300;  // silence between repeats
const int REPEAT_MAX = 3;

// "BUZZ chime 2" -> CHIME, 2. Repeat clamped to 1-3 (missing = 1). False if it isn't a known buzz.
inline bool parse(const String &cmd, Pattern &pattern, int &repeat) {
  if (!cmd.startsWith("BUZZ ")) return false;
  String rest = cmd.substring(5);
  rest.trim();
  int space = rest.indexOf(' ');
  String name = space < 0 ? rest : rest.substring(0, space);
  if (name == "chime") pattern = CHIME;
  else if (name == "alert") pattern = ALERT;
  else return false;
  repeat = space < 0 ? 1 : constrain((int)rest.substring(space + 1).toInt(), 1, REPEAT_MAX);
  return true;
}

// Steps through a pattern without blocking: start() it, then call update() often (every loop()).
// out(hz) is called on each change, 0 = off.
class Player {
 public:
  explicit Player(void (*out)(uint16_t hz)) : out_(out) {}

  void start(const Pattern &pattern, int repeat) {
    pattern_ = pattern;
    left_ = repeat;
    index_ = 0;
    gap_ = false;
    begin(millis());
  }

  bool playing() const { return left_ > 0; }

  void stop() {
    left_ = 0;
    out_(0);
  }

  void update() {
    if (!left_) return;
    uint32_t now = millis();
    if (now - since_ < length_) return;
    if (gap_) {
      gap_ = false;
    } else if (++index_ >= pattern_.count) {
      index_ = 0;
      if (--left_ == 0) {
        out_(0);
        return;
      }
      gap_ = true;
    }
    begin(now);
  }

 private:
  void begin(uint32_t now) {
    since_ = now;
    length_ = gap_ ? REPEAT_GAP_MS : pattern_.notes[index_].ms;
    out_(gap_ ? 0 : pattern_.notes[index_].hz);
  }

  void (*out_)(uint16_t);
  Pattern pattern_ = CHIME;
  int left_ = 0;
  size_t index_ = 0;
  bool gap_ = false;
  uint32_t since_ = 0, length_ = 0;
};

}  // namespace buzz
