#include "host.h"
#include "application/video_conferencing.h"
#include "logger.h"
#include <cassert>
#include <filesystem>
#include <iostream>
#include <memory>

namespace fs = std::filesystem;

Host::Host(unsigned int id, std::shared_ptr<Link> tx_link,
           std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
           std::shared_ptr<CongestionControlInterface> cc,
           std::unique_ptr<RtxManagerInterface> rtx_mngr,
           std::unique_ptr<ApplicationInterface> app,
           const std::string& save_dir)
    : id_(id), tx_link_(tx_link), rx_link_(rx_link), pacer_(std::move(pacer)),
      cc_(cc), rtx_mngr_(std::move(rtx_mngr)), app_(std::move(app)),
      seq_num_(0), logger_((fs::path(save_dir) /
                            fs::path("pkt_log" + std::to_string(id_) + ".csv"))
                               .c_str()) {
  assert(tx_link_);
  assert(rx_link_);
  assert(pacer_);
  assert(cc_);
  assert(app_);
  app_->RegisterTransport(this);
}

void Host::Send() {
  while (true) {
    unsigned int pkt_size_byte = GetPktToSendSize();
    if (pkt_size_byte > 0 && pacer_->CanSend(pkt_size_byte)) {
      auto pkt = GetPktToSend();
      assert(pkt);
      pkt->SetTsPrevPktSent(ts_pkt_sent_);
      ts_pkt_sent_ = Clock::GetClock().Now();
      pkt->SetTsSent(ts_pkt_sent_);
      cc_->OnPktSent(pkt.get());
      if (rtx_mngr_) {
        rtx_mngr_->OnPktSent(pkt.get());
      }
      logger_.OnPktSent(pkt.get(), tx_link_->GetQsizeByte(),
                        rx_link_->GetQsizeByte());
      OnPktSent(pkt.get());
      tx_link_->Push(std::move(pkt));
      pacer_->OnPktSent(pkt_size_byte);
    } else {
      break;
    }
  }
}

void Host::Receive() {
  const Timestamp& now = Clock::GetClock().Now();
  std::unique_ptr<Packet> pkt = rx_link_->Pull();
  while (pkt) {
    pkt->SetTsRcvd(now);
    logger_.OnPktRcvd(pkt.get(), tx_link_->GetQsizeByte(),
                      rx_link_->GetQsizeByte());
    cc_->OnPktRcvd(pkt.get());
    if (rtx_mngr_) {
      rtx_mngr_->OnPktRcvd(pkt.get());
    }
    OnPktRcvd(pkt.get());
    app_->DeliverPkt(std::move(pkt));
    pkt = rx_link_->Pull();
  }
}

unsigned int Host::GetPktToSendSize() const {
  if (!queue_.empty()) {
    return queue_.front()->GetSizeByte();
  }
  unsigned int unack_pkt_size = rtx_mngr_ ? rtx_mngr_->GetPktToSendSize() : 0;
  return unack_pkt_size == 0 ? app_->GetPktToSendSize() : unack_pkt_size;
}

std::unique_ptr<Packet> Host::GetPktFromApplication() {
  auto pkt = std::make_unique<Packet>(app_->GetPktToSend());
  pkt->SetSeqNum(seq_num_);
  ++seq_num_;
  return pkt;
}

std::unique_ptr<Packet> Host::GetPktToSend() {
  if (!queue_.empty()) {
    auto pkt = std::move(queue_.front());
    queue_.pop_front();
    return pkt;
  }
  if (rtx_mngr_ && rtx_mngr_->GetPktToSendSize()) {
    return rtx_mngr_->GetPktToSend();
  }
  return GetPktFromApplication();
}

void Host::UpdateRate() {
  const Timestamp& now = Clock::GetClock().Now();
  const auto pacer_update_interval = pacer_->GetUpdateInterval();
  if (now.ToMicroseconds() == 0 ||
      (now - pacer_->GetTsLastPacingRateUpdate()) >= pacer_update_interval) {
    pacer_->SetPacingRate(cc_->GetEstRate(now, now + pacer_update_interval));

    // set target bitrate if host is a video sender
    auto video_sender = dynamic_cast<VideoSender*>(app_.get());
    if (video_sender) {
      // allocate rate
      auto rtx_qsize = rtx_mngr_ ? rtx_mngr_->GetPktQueueSizeByte() * 8 : 0;
      auto app_qsize = app_->GetPktQueueSizeByte() * 8;
      auto pacing_rate = pacer_->GetPacingRate();
      auto reserved_rate = Rate::FromBps((rtx_qsize + app_qsize) /
                                         pacer_update_interval.ToSeconds());
      auto target_bitrate =
          pacing_rate > reserved_rate ? pacing_rate - reserved_rate : Rate();
      // std::cout << now.ToMilliseconds()
      //           << ", pacing rate=" << pacing_rate.ToBps()
      //           << ", budget_byte=" << pacer_->GetBudget() / 8
      //           << ", reserved_rate=" << reserved_rate.ToBps()
      //           << ", rtx_qsize_byte=" << rtx_qsize / 8
      //           << ", app_qsize_byte=" << app_qsize / 8
      //           << ", target bps=" << target_bitrate.ToBps() << std::endl;
      video_sender->SetTargetBitrate(target_bitrate);
    }
  }
}

void Host::Tick() {
  UpdateRate();
  pacer_->Tick();
  app_->Tick();
  cc_->Tick();
  if (rtx_mngr_) {
    rtx_mngr_->Tick();
  }
  Send();
  Receive();
}

void Host::Reset() {
  if (rtx_mngr_) {
    rtx_mngr_->Reset();
  }
  cc_->Reset();
  pacer_->Reset();
  app_->Reset();
  UpdateRate();
  seq_num_ = 0;
  logger_.Reset();
}

void Host::Summary() {
  std::cout << "Host " << id_ << std::endl;
  logger_.Summary();
}
