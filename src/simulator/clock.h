#ifndef CLOCK_H
#define CLOCK_H

#include "timestamp.h"
#include <cassert>
#include <memory>
#include <vector>

class ClockObserverInterface {
public:
  ClockObserverInterface() {}

  virtual void Tick() = 0;
  virtual void Reset() = 0;
};

class Clock {

public:
  static Clock &GetClock() {
    static Clock instance; // Guaranteed to be destroyed.
                           // Instantiated on first use.
    return instance;
  }

  Clock(const Clock &) = delete;
  Clock(Clock &&) = delete;
  Clock &operator=(Clock const &) = delete;
  Clock &operator=(Clock &&) = delete;

  void Tick();
  void Reset();
  void Elapse(unsigned int sec);
  inline void SetResolution(unsigned int resol_us) { resol_us_ = resol_us; }
  inline const Timestamp &Now() { return ts_; }
  inline void
  RegisterObserver(std::shared_ptr<ClockObserverInterface> observer) {
    assert(observer);
    observers_.push_back(observer);
  }

  inline int ToSeconds() { return ts_.ToSeconds(); }
  inline int ToMilliseconds() { return ts_.ToMilliseconds(); }
  inline int ToMicroseconds() { return ts_.ToMicroseconds(); }

private:
  Clock() : ts_(0), resol_us_(1000) {}
  Timestamp ts_;
  unsigned int resol_us_;
  std::vector<std::shared_ptr<ClockObserverInterface>> observers_;
};
#endif // CLOCK_H
