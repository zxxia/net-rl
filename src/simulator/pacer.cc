#include "pacer.h"
#include "packet/packet.h"
#include <algorithm>

Pacer::Pacer(unsigned int max_budget_byte,
             unsigned int pacing_rate_update_step_ms)
    : max_budget_(max_budget_byte * 8), budget_(Packet::MSS * 8),
      pacing_rate_update_step_ms_(pacing_rate_update_step_ms),
      ts_last_rate_update_(0), ts_last_budget_update_(0), pacing_rate_(0) {}

void Pacer::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  TimestampDelta elapsed_time = now - ts_last_budget_update_;
  unsigned int budget_inc = static_cast<unsigned int>(pacing_rate_.ToBps() *
                                                      elapsed_time.ToSeconds());
  budget_ = std::min(max_budget_, budget_ + budget_inc);
  ts_last_budget_update_ = now;
}

void Pacer::Reset() {
  budget_ = Packet::MSS * 8;
  ts_last_budget_update_.SetUs(0);
  ts_last_rate_update_.SetUs(0);
  pacing_rate_.SetBps(0);
}
