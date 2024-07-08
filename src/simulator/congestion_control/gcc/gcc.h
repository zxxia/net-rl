#ifndef CONGESTION_CONTROL_GCC_GCC_H
#define CONGESTION_CONTROL_GCC_GCC_H

#include "congestion_control/congestion_control.h"
#include "congestion_control/gcc/delay_based_bwe.h"
#include "congestion_control/gcc/loss_based_bwe.h"

class GCC : public CongestionControlInterface {
public:
  GCC();
  void Tick() override;
  void Reset() override;

  void OnPktToSend(Packet*) override{};
  void OnPktSent(const Packet*) override{};
  void OnPktRcvd(const Packet* pkt) override;
  void OnPktLost(const Packet*) override{};
  Rate GetEstRate(const Timestamp&, const Timestamp&) override { return rate_; }

  Rate GetRemoteEstimatedRate() const { return delay_based_bwe_.GetRate(); }

  void OnFrameRcvd(
      const Timestamp& ts_frame_sent,       // time curr frame's last pkt sent
      const Timestamp& ts_frame_rcvd,       // time curr frame's last pkt rcvd
      const Timestamp& ts_prev_frame_sent,  // time prev frame's last pkt sent
      const Timestamp& ts_prev_frame_rcvd); // time prev frame's last pkt rcvd

private:
  static constexpr unsigned int GCC_START_RATE_KBPS = 100;
  Rate rate_;
  Rate bwe_incoming_;
  DelayBasedBwe delay_based_bwe_;
  LossBasedBwe loss_based_bwe_;
};

#endif // CONGESTION_CONTROL_GCC_GCC_H
