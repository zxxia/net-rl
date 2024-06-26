#include "pacer.h"
#include "packet/packet.h"
#include <algorithm>

Pacer::Pacer(unsigned int max_budget_byte,
             unsigned int pacing_rate_update_step_ms)
    : max_budget_byte_(max_budget_byte), budget_byte_(Packet::MSS),
      pacing_rate_update_step_ms_(pacing_rate_update_step_ms),
      ts_last_rate_update_(0), ts_last_budget_update_(0), pacing_rate_(0) {}

void Pacer::Tick() {
  const Timestamp &now = Clock::GetClock().Now();
  TimestampDelta elapsed_time = now - ts_last_budget_update_;
  unsigned int budget_inc_byte = static_cast<unsigned int>(
      pacing_rate_.ToBytePerSec() * elapsed_time.ToSeconds());
  budget_byte_ = std::min(max_budget_byte_, budget_byte_ + budget_inc_byte);
  ts_last_budget_update_ = now;
}

void Pacer::Reset() {
  budget_byte_ = Packet::MSS;
  ts_last_budget_update_.SetUs(0);
  ts_last_rate_update_.SetUs(0);
  pacing_rate_.SetBps(0);
}
