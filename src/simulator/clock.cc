#include "clock.h"

void Clock::Tick() {
  for (auto &obs : observers_) {
    obs->Tick();
  }
  ts_ = ts_ + TimestampDelta(resol_us_);
}

void Clock::Reset() {
  for (auto &obs : observers_) {
    obs->Reset();
  }
  ts_ = Timestamp::Zero();
}

void Clock::Elapse(unsigned int sec) {
  unsigned int ticks = sec * 1000 * 1000 / resol_us_;
  for (unsigned int i = 0; i < ticks; ++i) {
    Tick();
  }
}
