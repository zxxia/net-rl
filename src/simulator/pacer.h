#ifndef PACER_H
#define PACER_H
#include "clock.h"
#include "rate.h"
#include "timestamp.h"

class Pacer : public ClockObserverInterface {
public:
  Pacer(unsigned int max_budget_byte, unsigned int pacing_rate_update_step_ms);

  void Tick() override;
  void Reset() override;
  inline void OnPktSent(unsigned pkt_size_byte) {
    budget_byte_ -= pkt_size_byte;
  }
  inline bool CanSend(unsigned pkt_size_byte) const {
    return pkt_size_byte <= budget_byte_ && pacing_rate_.ToBps() > 0;
  }
  inline void SetPacingRate(Rate rate) {
    pacing_rate_ = rate;
    ts_last_rate_update_ = Clock::GetClock().Now();;
  }
  inline Rate GetPacingRate() const { return pacing_rate_; }
  inline Timestamp GetTsLastBudgetUpdate() const {
    return ts_last_budget_update_;
  }
  inline Timestamp GetTsLastPacingRateUpdate() const {
    return ts_last_rate_update_;
  }
  inline TimestampDelta GetUpdateInterval() const {
    return TimestampDelta::FromMilliseconds(pacing_rate_update_step_ms_);
  }

private:
  unsigned int max_budget_byte_;
  unsigned int budget_byte_;
  unsigned int pacing_rate_update_step_ms_;
  Timestamp ts_last_rate_update_;
  Timestamp ts_last_budget_update_;
  Rate pacing_rate_;
};

#endif // PACER_H
