#ifndef CONGESTION_CONTROL_GCC_DELAY_BASED_BWE_H
#define CONGESTION_CONTROL_GCC_DELAY_BASED_BWE_H

#include "congestion_control/gcc/arrival_time_filter.h"
#include "packet/rtp_packet.h"
#include <vector>

class DelayBasedBwe {

public:
  DelayBasedBwe(const Rate& start_rate);
  void OnPktRcvd(const RtpPacket* pkt);
  void OnFrameRcvd(
      const Timestamp& ts_frame_sent,       // time curr frame's last pkt sent
      const Timestamp& ts_frame_rcvd,       // time curr frame's last pkt rcvd
      const Timestamp& ts_prev_frame_sent,  // time prev frame's last pkt sent
      const Timestamp& ts_prev_frame_rcvd); // time prev frame's last pkt rcvd

  inline Rate GetRate() const { return rate_; }

private:

  static constexpr double START_DELAY_GRADIENT_THRESH_MS = 5.0;
  static constexpr unsigned int OVERUSE_THRESH_MS = 100;
  static constexpr unsigned int HISTORY_WINDOW_MS = 500;
  static constexpr double K_U = 0.01;
  static constexpr double K_D = 0.00018;
  static constexpr double ALPHA = 0.85;
  static constexpr double ETA = 1.05;

  enum class RateControlState { DEC, HOLD, INC };
  enum class BwUsageSignal { UNDERUSE, NORMAL, OVERUSE };

  void UpdateState();
  void UpdateBwOveruseSignal();
  void UpdateRate();

  // variables for recv rate calculation
  std::vector<unsigned int> pkt_size_wnd_; // pkt size rcvd in past WND ms
  std::vector<Timestamp> ts_rcvd_wnd_;     // pkt ts_rcvd in past WND ms
  Rate rcv_rate_;               // computed receiving rate

  // variables for delay gradient and gradient threshold estimation
  double delay_grad_thresh_ms_; // gamma in GCC paper
  double delay_grad_ms_;        // delay gradient
  double delay_grad_hat_ms_;    // delay gradient hat
  ArrivalTimeFilter filter_;

  // variables for bw overuse detection
  BwUsageSignal sig_;
  BwUsageSignal new_sig_;
  Timestamp ts_overuse_start_;


  // variables for delay gradient and gradient threshold estimation
  RateControlState state_;
  Timestamp rate_update_ts_;
  Rate rate_; // estimated sending rate

};
#endif // CONGESTION_CONTROL_GCC_DELAY_BASED_BWE_H
