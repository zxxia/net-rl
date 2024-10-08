#include "rtx_manager/rtp_rtx_manager.h"
#include "packet/rtp_packet.h"

void RtpRtxManager::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  if (now - ts_last_clean_ >= TimestampDelta::FromSeconds(1)) {
    std::vector<unsigned int> seq2erase;
    for(auto it = buffer_.begin(); it != buffer_.end(); ++it) {
      if (now - it->second.pkt->GetTsSent() > TimestampDelta::FromSeconds(1)) {
        seq2erase.emplace_back(it->first);
      }
    }
    for (auto&& seq : seq2erase) {
      buffer_.erase(seq);
      if (auto it = rtx_queue_.find(seq); it != rtx_queue_.end()) {
        rtx_queue_.erase(it);
      }
    }
    ts_last_clean_ = now;
  }
}

void RtpRtxManager::Reset() {
  buffer_.clear();
  rtx_queue_.clear();
  ts_last_clean_.SetUs(0);
}

void RtpRtxManager::OnPktSent(const Packet* pkt) {
  if (auto vid_data = dynamic_cast<const VideoData*>(pkt->GetApplicationData());
      vid_data && vid_data->padding) {
    // ignore padding packet
    return;
  }
  if (auto rtp_pkt = dynamic_cast<const RtpPacket*>(pkt); rtp_pkt) {
    auto seq = rtp_pkt->GetSeqNum();
    if (auto it = buffer_.find(seq); it == buffer_.end()) {
      // rtp pkt not in buffer, add into the buffer
      auto res = buffer_.emplace(seq, RtxInfo());
      if (res.second) {
        auto& rtx_info = res.first->second;
        rtx_info.pkt = std::make_unique<RtpPacket>(*rtp_pkt);
        // rtx_info.rto = rto_;
      }
    } else {
      // rtp pkt already in buffer, update pkt
      auto& rtx_info = it->second;
      rtx_info.num_rtx++;
      *(rtx_info.pkt) = *pkt;
    }
  }
}

void RtpRtxManager::OnPktRcvd(const Packet* pkt) {
  auto nack = dynamic_cast<const RtpNackPacket*>(pkt);
  if (!nack) { // if not rtp nack pkt, return
    return;
  }
  auto seq = nack->GetNackNum();
  if (auto it = buffer_.find(seq); it != buffer_.end()) {
    rtx_queue_.insert(seq);
  }
}

unsigned int RtpRtxManager::GetPktToSendSize() {
  if (rtx_queue_.empty()) {
    return 0;
  }
  auto seq = *rtx_queue_.begin();
  auto it = buffer_.find(seq);
  assert(it != buffer_.end());
  return it->second.pkt->GetSizeByte();
}

std::unique_ptr<Packet> RtpRtxManager::GetPktToSend() {
  if (rtx_queue_.empty()) {
    return nullptr;
  }
  auto seq = *rtx_queue_.begin();
  rtx_queue_.erase(seq);
  auto it = buffer_.find(seq);
  assert(it != buffer_.end());
  auto rtp_pkt = dynamic_cast<const RtpPacket*>(it->second.pkt.get());
  return std::make_unique<RtpPacket>(*(rtp_pkt));
}

unsigned int RtpRtxManager::GetPktQueueSizeByte() {
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
