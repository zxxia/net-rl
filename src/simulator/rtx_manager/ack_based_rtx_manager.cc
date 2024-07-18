#include "rtx_manager/ack_based_rtx_manager.h"
#include "clock.h"
#include "packet/packet.h"
#include <cassert>
#include <memory>

AckBasedRtxManager::AckBasedRtxManager(
    std::shared_ptr<CongestionControlInterface> cc)
    : cc_(std::move(cc)), max_ack_num_(-1), rto_(3000000) {
  assert(cc_ && "cc should not be a nullptr!");
}

void AckBasedRtxManager::Tick() {}

void AckBasedRtxManager::Reset() {
  buffer_.clear();
  rtx_queue_.clear();
  max_ack_num_ = -1;

  srtt_ = TimestampDelta::Zero();
  rttvar_ = TimestampDelta::Zero();
  rto_ = TimestampDelta::Zero();
}

void AckBasedRtxManager::OnPktSent(const Packet* pkt) {
  if (dynamic_cast<const AckPacket*>(pkt)) {
    // do nothing if the pkt is ack
    return;
  }
  if (auto vid_data = dynamic_cast<const VideoData*>(pkt->GetApplicationData());
      vid_data && vid_data->padding) {
    // ignore padding packet
    return;
  }
  unsigned int seq = pkt->GetSeqNum();
  if (auto it = buffer_.find(seq); it != buffer_.end()) { // pkt in buffer
    auto& rtx_info = it->second;
    rtx_info.num_rtx++;
    // update the pkt in the rtx buffer
    *(rtx_info.pkt) = *pkt;
  } else { // pkt is not in rtx buffer yet so add
    auto res = buffer_.emplace(seq, RtxInfo());
    if (res.second) {
      auto& rtx_info = res.first->second;
      rtx_info.pkt = std::make_unique<Packet>(*pkt);
      rtx_info.rto = rto_;
    }
  }
}

void AckBasedRtxManager::OnPktRcvd(const Packet* pkt) {
  // As to why - these are Stroustrup's words from the D & E book,
  // section 14.2.2: I use a reference cast when I want an assumption about a
  // reference type checked and consider it a failure for my assumption to be
  // wrong. If instead I want to select among plausible alternatives, I use a
  // pointer cast and test the result.
  auto ack = dynamic_cast<const AckPacket*>(pkt);
  if (!ack) { // if not ack pkt, return
    return;
  }

  unsigned int ack_num = ack->GetAckNum();
  if (auto it = buffer_.find(ack_num); it != buffer_.end()) {
    // remove the cached data pkt from buffer
    buffer_.erase(it);
  } else {
    // this data packet is already acked and removed from buffer
    return;
  }

  // detect lost/missing packet
  for (unsigned int seq = static_cast<unsigned int>(max_ack_num_ + 1);
       seq < ack_num; seq++) {
    auto it = buffer_.find(seq);
    if (it == buffer_.end()) {
      continue;
    }
    auto& rtx_info = it->second;
    const Packet* data_pkt = rtx_info.pkt.get();

    if ((rtx_info.num_rtx == 0 ||
         Clock::GetClock().Now() - data_pkt->GetTsSent() > rtx_info.rto) &&
        rtx_queue_.find(seq) == rtx_queue_.end()) {
      cc_->OnPktLost(data_pkt);
      rtx_queue_.insert(seq);
    }
  }

  // sync seq nums waiting in rtx queue and the rtx buffer
  std::vector<unsigned int> seq2erase;
  for (auto it = rtx_queue_.begin(); it != rtx_queue_.end(); ++it) {
    if (buffer_.find(*it) == buffer_.end()) {
      seq2erase.emplace_back(*it);
    }
  }

  for (auto&& seq : seq2erase) {
    rtx_queue_.erase(seq);
  }

  max_ack_num_ = ack_num == static_cast<unsigned int>(max_ack_num_ + 1)
                     ? ack_num
                     : max_ack_num_;

  // update rto estimation
  UpdateRTO(*ack);
}

unsigned int AckBasedRtxManager::GetPktToSendSize() {
  if (rtx_queue_.empty()) {
    return 0;
  }
  auto seq = *rtx_queue_.begin();
  auto it = buffer_.find(seq);
  assert(it != buffer_.end());
  return it->second.pkt->GetSizeByte();
}

std::unique_ptr<Packet> AckBasedRtxManager::GetPktToSend() {
  if (rtx_queue_.empty()) {
    return nullptr;
  }
  auto seq = *rtx_queue_.begin();
  rtx_queue_.erase(seq);
  auto it = buffer_.find(seq);
  assert(it != buffer_.end());
  return std::make_unique<Packet>(*(it->second.pkt));
}

void AckBasedRtxManager::UpdateRTO(const AckPacket& ack) {
  TimestampDelta rtt = ack.GetRTT();
  if (srtt_.IsZero() and rttvar_.IsZero()) {
    srtt_ = rtt;
    rttvar_ = rtt / 2;
  } else {
    srtt_ = srtt_ * (1.0 - SRTT_ALPHA) + rtt * SRTT_ALPHA;
    TimestampDelta abs_diff = srtt_ > rtt ? srtt_ - rtt : rtt - srtt_;
    rttvar_ = rttvar_ * (1 - SRTT_BETA) + abs_diff * SRTT_BETA;
  }
  rto_ = std::max(
      TimestampDelta::FromSeconds(1),
      std::min(srtt_ + rttvar_ * RTO_K, TimestampDelta::FromSeconds(60)));
}

unsigned int AckBasedRtxManager::GetPktQueueSizeByte() {
  unsigned int sum = 0;
  std::vector<unsigned int> seq2erase;
  for (auto it = rtx_queue_.begin(); it != rtx_queue_.end(); ++it) {
    if (auto kv = buffer_.find(*it); kv != buffer_.end()) {
      sum += kv->second.pkt->GetSizeByte();
    } else {
      seq2erase.emplace_back(kv->first);
    }
  }
  for (auto&& seq : seq2erase) {
    rtx_queue_.erase(seq);
  }
  return sum;
}
