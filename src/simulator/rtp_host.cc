#include "rtp_host.h"
#include "application/video_conferencing.h"
#include "congestion_control/gcc/gcc.h"
#include "packet/rtp_packet.h"
#include "utils.h"
#include <iostream>
#include <memory>
#include <vector>

void NackModule::OnPktRcvd(unsigned int seq, unsigned int max_seq) {
  pkts_lost_.erase(seq);
  if (seq < max_seq) {
    return;
  }
  AddMissing(max_seq + 1, seq);
}

void NackModule::GenerateNacks(std::vector<unsigned int>& nacks,
                               unsigned int max_seq,
                               const TimestampDelta& rtt) {
  const Timestamp& now = Clock::GetClock().Now();
  std::vector<unsigned int> k2erase;
  for (auto it = pkts_lost_.begin(); it != pkts_lost_.end(); it++) {
    if (it->second.retries >= 10) {
      k2erase.emplace_back(it->first);
    }
    auto seq = it->first;
    if (seq < max_seq &&
        (!it->second.retries || now - it->second.ts_sent >= rtt * 1.5)) {
      nacks.emplace_back(seq);
    }
  }
  std::sort(nacks.begin(), nacks.end());
  for (auto&& k : k2erase) {
    pkts_lost_.erase(k);
  }
}

void NackModule::OnNackSent(unsigned int seq) {
  if (auto it = pkts_lost_.find(seq); it != pkts_lost_.end()) {
    it->second.retries += 1;
    it->second.ts_sent = Clock::GetClock().Now();
  }
}

void NackModule::CleanUpTo(unsigned int max_seq) {
  std::vector<unsigned int> seq2erase;
  for (auto it = pkts_lost_.begin(); it != pkts_lost_.end(); it++) {
    if (it->first < max_seq) {
      seq2erase.emplace_back(it->first);
    }
  }
  for (auto&& seq : seq2erase) {
    pkts_lost_.erase(seq);
  }
}

void NackModule::AddMissing(unsigned int from_seq, unsigned int to_seq) {
  for (auto seq = from_seq; seq < to_seq; seq++) {
    if (auto it = pkts_lost_.find(seq); it == pkts_lost_.end()) {
      pkts_lost_.emplace(seq, NackInfo());
    }
  }
}

RtpHost::RtpHost(unsigned int id, std::shared_ptr<Link> tx_link,
                 std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
                 std::shared_ptr<CongestionControlInterface> cc,
                 std::unique_ptr<RtpRtxManager> rtx_mngr,
                 std::unique_ptr<ApplicationInterface> app,
                 const std::string& save_dir)
    : Host{id,
           tx_link,
           rx_link,
           std::move(pacer),
           cc,
           std::move(rtx_mngr),
           std::move(app),
           save_dir},
      owd_ms_(0) {}

void RtpHost::OnFrameRcvd(const Frame& frame, const Frame& prev_frame) {
  if (auto gcc = dynamic_cast<GCC*>(cc_.get()); gcc) {
    gcc->OnFrameRcvd(frame.last_pkt_sent_ts, frame.last_pkt_rcvd_ts,
                     prev_frame.last_pkt_sent_ts, prev_frame.last_pkt_rcvd_ts);
  }
  if (!frame.pkts_rcvd.empty()) {
    nack_module_.CleanUpTo(*frame.pkts_rcvd.rbegin());
  }
}

void RtpHost::OnPktSent(Packet* pkt) {
  if (auto nack = dynamic_cast<RtpNackPacket*>(pkt); nack) {
    nack_module_.OnNackSent(nack->GetNackNum());
  }
}

void RtpHost::OnPktRcvd(Packet* pkt) {
  if (auto rtp_pkt = dynamic_cast<RtpPacket*>(pkt); rtp_pkt) {
    auto seq = rtp_pkt->GetSeqNum();
    if (state_.received == 0) {
      // receive the 1st pkt so set base seq
      state_.base_seq = seq;
      state_.max_seq = state_.base_seq;
    }
    nack_module_.OnPktRcvd(seq, state_.max_seq);
    state_.max_seq = std::max(state_.max_seq, seq);

    // ignore rtx packets as in real RTP rtx packets are sent in different
    // rtp ssrc stream or different rtp session
    state_.received += static_cast<int>(pkt->IsRtx());
    // TODO: here is an inconsistency between received and bytes_received
    state_.bytes_received += rtp_pkt->GetSizeByte();

    owd_ms_ = rtp_pkt->GetDelayMs();
    sender_rtt_ = rtp_pkt->GetRTT();
    // std::cout << "rcv rtp pkt " << pkt->GetDelayMs() << std::endl;
    std::vector<unsigned int> nacks;
    nack_module_.GenerateNacks(nacks, state_.max_seq, sender_rtt_);
    SendNacks(nacks);
  } else if (auto rtcp_pkt = dynamic_cast<RtcpPacket*>(pkt); rtcp_pkt) {
    state_.rtt = TimestampDelta::FromMilliseconds(rtcp_pkt->GetOwd() +
                                                  rtcp_pkt->GetDelayMs());
  } else {
    // std::cout << "rcv other pkt\n";
  }
}

std::unique_ptr<Packet> RtpHost::GetPktFromApplication() {
  auto pkt = std::make_unique<RtpPacket>(app_->GetPktToSend());
  pkt->SetSeqNum(seq_num_);
  pkt->SetRTT(state_.rtt);
  ++seq_num_;
  return pkt;
};

void RtpHost::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  Host::Tick();
  if ((now - last_rtcp_report_ts_) >=
      TimestampDelta::FromMilliseconds(RTCP_INTERVAL_MS)) {
    Rate remb_rate;
    if (const auto gcc = dynamic_cast<const GCC*>(cc_.get());
        gcc && (now - last_remb_ts_) >=
                   TimestampDelta::FromMilliseconds(REMB_INTERVAL_MS)) {
      remb_rate = gcc->GetRemoteEstimatedRate();
      last_remb_ts_ = now;
    }
    // std::cout << last_rtcp_report_ts_.ToMicroseconds() << " " <<
    // now.ToMicroseconds() << std::endl;
    SendRTCPReport(remb_rate);
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
  state_.rtt = TimestampDelta::Zero();
  nack_module_.Reset();
  sender_rtt_ = TimestampDelta::Zero();
  Host::Reset();
}

void RtpHost::SendRTCPReport(const Rate& remb_rate) {
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
  double loss_frac = expected_interval > 0 && lost_interval > 0
                         ? static_cast<double>(lost_interval) /
                               static_cast<double>(expected_interval)
                         : 0.0;
  Rate tput = Rate::FromBytePerSec(
      (state_.bytes_received - state_.bytes_received_prior) * 1000 /
      RTCP_INTERVAL_MS);
  state_.bytes_received_prior = state_.bytes_received;
  // TODO: RtcpPacket size
  auto& pkt = queue_.emplace_back(std::make_unique<RtcpPacket>(1, loss_frac));
  auto report = static_cast<RtcpPacket*>(pkt.get());
  report->SetOwd(owd_ms_);
  report->SetTput(tput);
  report->SetRembRate(remb_rate);

  // std::cout << "Host: " << id_ << " send rtcp report loss=" << loss_fraction
  //           << " " << owd_ms_ << std::endl;
}

void RtpHost::SendNacks(std::vector<unsigned int>& nacks) {
  for (auto&& seq : nacks) {
    queue_.emplace_back(std::make_unique<RtpNackPacket>(seq));
  }
}
