#ifndef Link_H
#define Link_H

#include "clock.h"
#include "packet/packet.h"
#include <deque>
#include <memory>
#include <vector>

class Link : public ClockObserverInterface {
public:
  Link(std::vector<Timestamp> ts, std::vector<double> bw_mbps,
       unsigned int prop_delay_ms, double random_loss_rate,
       unsigned int qcap_byte)
      : ts_(ts), bw_mbps_(bw_mbps), prop_delay_ms_(prop_delay_ms),
        random_loss_rate_(random_loss_rate), qcap_byte_(qcap_byte),
        qsize_byte_(0), last_budget_update_ts_(0), budget_bit_(0) {}

  Link(const char* fname);

  void Push(std::unique_ptr<Packet> pkt);
  std::unique_ptr<Packet> Pull();
  void Tick() override;
  void Reset() override;

  inline unsigned int GetQsizeByte() const { return qsize_byte_; }
  inline unsigned int GetQsizePkt() const { return queue_.size(); }
  double GetAvgBwMbps() const;
  unsigned int GetAvailBitsToSend(const Timestamp& t0,
                                  const Timestamp& t1) const;
  inline unsigned int GetPropDelayMs() const { return prop_delay_ms_; }

  inline void SetPropDelayMs(unsigned int delay_ms) {
    prop_delay_ms_ = delay_ms;
  }

  inline void SetQueueCap(unsigned int bytes) {
    qcap_byte_ = bytes;
  }

private:
  void UpdateBwBudget();

  std::vector<Timestamp> ts_;
  std::vector<double> bw_mbps_;
  unsigned int prop_delay_ms_;
  double random_loss_rate_;
  unsigned int qcap_byte_;
  unsigned int qsize_byte_;
  Timestamp last_budget_update_ts_;
  unsigned int budget_bit_;

  std::deque<std::unique_ptr<Packet>> queue_;
  std::deque<std::unique_ptr<Packet>> ready_pkts_;
};

#endif // Link_H
