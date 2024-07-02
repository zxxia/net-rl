#include "rtp_host.h"
#include "application/video_conferencing.h"
#include "packet/rtp_packet.h"
#include "utils.h"
#include <iostream>
#include <memory>

RtpHost::RtpHost(unsigned int id, std::shared_ptr<Link> tx_link,
                 std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
                 std::shared_ptr<CongestionControlInterface> cc,
          std::unique_ptr<RtxManager> rtx_mngr,
                 std::unique_ptr<ApplicationInterface> app,
                 std::shared_ptr<Logger> logger)
    : Host{id,
           tx_link,
           rx_link,
           std::move(pacer),
           cc,
           std::move(rtx_mngr),
           std::move(app),
           logger},
      owd_ms_(0) {}

void RtpHost::OnPktRcvd(std::unique_ptr<Packet> pkt) {
  if (instanceof <RtpPacket>(pkt.get())) {
    if (state_.received == 0) {
      // receive the 1st pkt so set base seq
      state_.base_seq = pkt->GetSeqNum();
      state_.max_seq = state_.base_seq;
    }
    // self.nack_module.on_pkt_rcvd(pkt, self.max_pkt_id)
    state_.max_seq = std::max(state_.max_seq, pkt->GetSeqNum());
    // TODO: verify the line below
    state_.received += 1; // int(pkt.ts_first_sent_ms == pkt.ts_sent_ms)
    state_.bytes_received += pkt->GetSizeByte();

    owd_ms_ = pkt->GetDelayMs();
    // owd_ms_.emplace_back(pkt->GetDelayMs());
    // std::cout << "rcv rtp pkt " << pkt->GetDelayMs() << std::endl;
    app_->DeliverPkt(std::move(pkt));
    // pkt_ids = self.nack_module.generate_nack(self.max_pkt_id)
    // self.send_nack(pkt_ids)
  } else if (instanceof <RtcpPacket>(pkt.get())) {
    // std::cout << "rcv rtcp pkt\n";
  } else {
    // std::cout << "rcv other pkt\n";
  }
}

std::unique_ptr<Packet> RtpHost::GetPktFromApplication() {
  auto pkt = std::make_unique<RtpPacket>(app_->GetPktToSend());
  pkt->SetSeqNum(seq_num_);
  ++seq_num_;
  return pkt;
};

void RtpHost::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  Host::Tick();
  if ((now - last_rtcp_report_ts_) >=
      TimestampDelta::FromMilliseconds(RTCP_INTERVAL_MS)) {
    // std::cout << last_rtcp_report_ts_.ToMicroseconds() << " " <<
    // now.ToMicroseconds() << std::endl;
    SendRTCPReport();
    last_rtcp_report_ts_ = now;
  }
}

void RtpHost::Reset() {
  last_rtcp_report_ts_.SetUs(0);
  state_.max_seq = 0;
  state_.base_seq = 0;
  state_.received = 0;
  state_.expected_prior = 0;
  state_.received_prior = 0;
  state_.bytes_received = 0;
  state_.bytes_received_prior = 0;
  Host::Reset();
}

void RtpHost::SendRTCPReport() {
  if (instanceof <VideoSender>(app_.get())) {
    return;
  }
  unsigned int expected = state_.max_seq - state_.base_seq + 1;
  // unsigned int lost_pkt_cnt = expected - state_.received;
  unsigned int expected_interval = expected - state_.expected_prior;
  state_.expected_prior = expected;
  unsigned int received_interval = state_.received - state_.received_prior;
  state_.received_prior = state_.received;
  int lost_interval =
      static_cast<int>(expected_interval) - static_cast<int>(received_interval);
  double loss_fraction = expected_interval > 0 && lost_interval > 0
                             ? static_cast<double>(lost_interval) /
                                   static_cast<double>(expected_interval)
                             : 0.0;
  Rate tput = Rate::FromBytePerSec(
      (state_.bytes_received - state_.bytes_received_prior) * 1000 /
      RTCP_INTERVAL_MS);
  state_.bytes_received_prior = state_.bytes_received;
  // TODO: RtcpPacket size
  auto& report =
      queue_.emplace_back(std::make_unique<RtcpPacket>(1, loss_fraction));
  static_cast<RtcpPacket*>(report.get())->SetOwd(owd_ms_);
  static_cast<RtcpPacket*>(report.get())->SetTput(tput);
  // static_cast<RtcpPacket*>(report.get())->LoadOwd(owd_ms_);

  // std::cout << "Host: " << id_ << " send rtcp report loss=" << loss_fraction
  //           << " " << owd_ms_ << std::endl;
}
