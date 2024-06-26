#include "application/video_conferencing.h"
#include "host.h"
#include "logger.h"
#include <cassert>
#include <iostream>
#include <memory>

Host::Host(unsigned int id, std::shared_ptr<Link> tx_link,
           std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
           std::unique_ptr<CongestionControlInterface> cc,
           std::unique_ptr<ApplicationInterface> app,
           std::shared_ptr<Logger> logger)
    : id_(id), tx_link_(tx_link), rx_link_(rx_link), pacer_(std::move(pacer)),
      cc_(std::move(cc)), app_(std::move(app)), logger_(logger), seq_num_(0) {
  assert(tx_link_);
  assert(rx_link_);
  assert(pacer_);
  assert(cc_);
  assert(app_);
  UpdateRate();
}

void Host::OnPktRcvd(std::unique_ptr<Packet> pkt) {
  app_->DeliverPkt(std::move(pkt));
}

void Host::Send() {
  while (true) {
    unsigned int pkt_size_byte = GetPktToSendSize();
    if (pkt_size_byte > 0 && pacer_->CanSend(pkt_size_byte)) {
      auto pkt = GetPktToSend();
      assert(pkt);
      pkt->SetSeqNum(seq_num_);
      pkt->SetTsPrevPktSent(ts_pkt_sent_);
      ts_pkt_sent_ = Clock::GetClock().Now();
      pkt->SetTsSent(ts_pkt_sent_);
      if (logger_) {
        logger_->OnPktSent(*pkt);
      }
      tx_link_->Push(std::move(pkt));
      ++seq_num_;
      pacer_->OnPktSent(pkt_size_byte);
    } else {
      break;
    }
  }
}

void Host::Receive() {
  const Timestamp &now = Clock::GetClock().Now();
  std::unique_ptr<Packet> pkt = rx_link_->Pull();
  while (pkt) {
    pkt->SetTsRcvd(now);
    if (logger_) {
      logger_->OnPktRcvd(*pkt);
    }
    cc_->OnPktRcvd(pkt.get());
    // TODO: rtx OnPktRcvd
    OnPktRcvd(std::move(pkt));
    pkt = rx_link_->Pull();
  }
}

unsigned int Host::GetPktToSendSize() const {
  if (!queue_.empty()) {
    return queue_.front()->GetSizeByte();
  }
  return app_->GetPktToSendSize();
}

std::unique_ptr<Packet> Host::GetPktFromApplication() {
  return std::make_unique<Packet>(app_->GetPktToSend());
}

std::unique_ptr<Packet> Host::GetPktToSend() {
  // TODO: fix this
  if (!queue_.empty()) {
    auto pkt = std::move(queue_.front());
    queue_.pop_front();
    return pkt;
  }
  return GetPktFromApplication();
}

void Host::UpdateRate() {
  const Timestamp &now = Clock::GetClock().Now();
  if (now.ToMicroseconds() == 0 || (now - pacer_->GetTsLastPacingRateUpdate()) >=
      pacer_->GetUpdateInterval()) {
    pacer_->SetPacingRate(
        cc_->GetEstRate(now, now + pacer_->GetUpdateInterval()));
  }
  // set target bitrate if host0 is a video sender
  auto video_sender = dynamic_cast<VideoSender*>(app_.get());
  if (video_sender) {
    video_sender->SetTargetBitrate(pacer_->GetPacingRate());
  }
}

void Host::Tick() {
  pacer_->Tick();
  UpdateRate();
  app_->Tick();
  cc_->Tick();
  Send();
  Receive();
}

void Host::Reset() {
  cc_->Reset();
  pacer_->Reset();
  app_->Reset();
  UpdateRate();
  seq_num_ = 0;
  if (logger_) {
    logger_->Reset();
  }
}
