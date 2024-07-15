#include "congestion_control/gcc/gcc.h"
#include <filesystem>

namespace fs = std::filesystem;

GCC::GCC(unsigned int id, const std::string& save_dir)
    : rate_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      bwe_incoming_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      delay_based_bwe_(Rate::FromKbps(GCC_START_RATE_KBPS)),
      loss_based_bwe_(Rate::FromKbps(GCC_START_RATE_KBPS)), id_(id),
      save_dir_(save_dir) {
  fs::create_directories(save_dir_);
  fs::path dir(save_dir_);
  fs::path file("gcc_log_" + std::to_string(id_) + ".csv");
  stream_.open((dir / file).c_str(), std::fstream::out | std::fstream::trunc);
  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
}

void GCC::Tick() {}

void GCC::Reset() {
  rate_ = Rate::FromKbps(GCC_START_RATE_KBPS);
  bwe_incoming_ = Rate::FromKbps(GCC_START_RATE_KBPS);
  delay_based_bwe_.Reset(Rate::FromKbps(GCC_START_RATE_KBPS));
  loss_based_bwe_.Reset(Rate::FromKbps(GCC_START_RATE_KBPS));
  stream_.close();
  fs::path dir(save_dir_);
  fs::path file("gcc_log_" + std::to_string(id_) + ".csv");
  stream_.open((dir / file).c_str(), std::fstream::out | std::fstream::trunc);
  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
}

void GCC::OnPktRcvd(const Packet* pkt) {
  if (auto rtp_pkt = dynamic_cast<const RtpPacket*>(pkt); rtp_pkt) {
    delay_based_bwe_.OnPktRcvd(rtp_pkt);
  } else if (auto rtcp_pkt = dynamic_cast<const RtcpPacket*>(pkt); rtcp_pkt) {
    // call loss based
    loss_based_bwe_.OnPktLoss(rtcp_pkt->GetLossFraction());
    Rate bwe_incoming = rtcp_pkt->GetRembRate();
    if (!bwe_incoming.IsZero()) {
      bwe_incoming_ = bwe_incoming;
    }
    rate_ = std::min(loss_based_bwe_.GetRate(), bwe_incoming_);
    loss_based_bwe_.SetRate(rate_);
    stream_ << Clock::GetClock().Now().ToMicroseconds() << "," << rate_.ToBps()
            << "," << loss_based_bwe_.GetRate().ToBps() << ","
            << delay_based_bwe_.GetRate().ToBps() << ","
            << delay_based_bwe_.GetRateControlState() << ","
            << delay_based_bwe_.GetDelayGrad() << ","
            << delay_based_bwe_.GetDelayGradHat() << ","
            << delay_based_bwe_.GetDelayGradThresh() << ","
            << delay_based_bwe_.GetRcvRate().ToBps() << ","
            << delay_based_bwe_.GetBwUsageSignal() << ","
            << rtcp_pkt->GetLossFraction() << std::endl;
  } else {
  }
}

void GCC::OnFrameRcvd(const Timestamp& ts_frame_sent,
                      const Timestamp& ts_frame_rcvd,
                      const Timestamp& ts_prev_frame_sent,
                      const Timestamp& ts_prev_frame_rcvd) {
  delay_based_bwe_.OnFrameRcvd(ts_frame_sent, ts_frame_rcvd, ts_prev_frame_sent,
                               ts_prev_frame_rcvd);

  stream_ << Clock::GetClock().Now().ToMicroseconds() << "," << rate_.ToBps()
          << "," << loss_based_bwe_.GetRate().ToBps() << ","
          << delay_based_bwe_.GetRate().ToBps() << ","
          << delay_based_bwe_.GetRateControlState() << ","
          << delay_based_bwe_.GetDelayGrad() << ","
          << delay_based_bwe_.GetDelayGradHat() << ","
          << delay_based_bwe_.GetDelayGradThresh() << ","
          << delay_based_bwe_.GetRcvRate().ToBps() << ","
          << delay_based_bwe_.GetBwUsageSignal() << ","
          << 0 << std::endl;
}
