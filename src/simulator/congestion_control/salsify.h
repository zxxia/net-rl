#ifndef SALSIFY_H
#define SALSIFY_H

#include "congestion_control/congestion_control.h"
class Salsify : public CongestionControlInterface {
public:
  Salsify();
  Salsify(unsigned int fps);
  void Tick() override;
  void Reset() override;

  void OnPktToSend(Packet*) override{};
  void OnPktSent(const Packet*) override;
  void OnPktRcvd(const Packet* pkt) override;
  void OnPktLost(const Packet*) override;
  Rate GetEstRate(const Timestamp&, const Timestamp&) override { return rate_; }


private:
  static constexpr unsigned int TARGET_E2E_DELAY_CAP_MS = 100;
  static constexpr unsigned int MIN_SENDING_RATE_KBPS = 50;

  // sender-side variables
  Rate rate_;
  int num_pkt_inflight_;
  unsigned int fps_;
};

#endif // SALSIFY_H
