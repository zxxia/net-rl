#include "congestion_control/gcc/gcc.h"

GCC::GCC()
    : rate_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      bwe_incoming_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      delay_based_bwe_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      loss_based_bwe_(Rate::FromKbps(GCC_START_RATE_KBPS)) {}

void GCC::Tick() {}

void GCC::Reset() {}

void GCC::OnPktRcvd(const Packet* pkt) {
  if (auto rtp_pkt = dynamic_cast<const RtpPacket*>(pkt); rtp_pkt) {
    delay_based_bwe_.OnPktRcvd(rtp_pkt);
  } else if (auto rtcp_pkt = dynamic_cast<const RtcpPacket*>(pkt); rtcp_pkt) {
    // call loss based
    loss_based_bwe_.OnPktLoss(rtcp_pkt->GetLossFraction());
    // std::cout << "remb=" << rtcp_pkt->GetRembRate().ToMbps()
    //           << ", loss_est_rate=" << loss_based_bwe_.GetRate().ToMbps()
    //           << std::endl;
    Rate bwe_incoming = rtcp_pkt->GetRembRate();
    if (!bwe_incoming.IsZero()) {
      bwe_incoming_ = bwe_incoming;
    }
    rate_ = std::min(loss_based_bwe_.GetRate(), bwe_incoming_);
  } else {
  }
}

void GCC::OnFrameRcvd(const Timestamp& ts_frame_sent,
                      const Timestamp& ts_frame_rcvd,
                      const Timestamp& ts_prev_frame_sent,
                      const Timestamp& ts_prev_frame_rcvd) {
  delay_based_bwe_.OnFrameRcvd(ts_frame_sent, ts_frame_rcvd, ts_prev_frame_sent,
                               ts_prev_frame_rcvd);
}
