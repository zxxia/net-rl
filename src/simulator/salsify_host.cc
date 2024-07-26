#include "salsify_host.h"
#include "application/video_conferencing.h"
#include "congestion_control/salsify.h"
#include "utils.h"

SalsifyHost::SalsifyHost(unsigned int id, std::shared_ptr<Link> tx_link,
                         std::shared_ptr<Link> rx_link,
                         std::unique_ptr<Pacer> pacer,
                         std::shared_ptr<CongestionControlInterface> cc,
                         std::unique_ptr<AckBasedRtxManager> rtx_mngr,
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
      tao_(-1) {
  auto vid_sndr = dynamic_cast<VideoSender*>(app_.get());
  auto vid_rcvr = dynamic_cast<VideoReceiver*>(app_.get());
  assert(vid_sndr || vid_rcvr);
  if (vid_sndr) {
    vid_sndr->DisablePadding();
    vid_sndr->MTUBasePacketize();
  }
  (void)vid_rcvr;
}

void SalsifyHost::OnPktSent(Packet* pkt) {
  if (instanceof <VideoSender>(app_.get())) {
    const Timestamp& now = Clock::GetClock().Now();
    if (pkt->GetTsPrevPktSent() == ts_last_burst_sent_end_) {
      // std::cout << "grace=" << (now -
      // ts_last_burst_sent_end_).ToMicroseconds()
      //           << ", "
      //           << 1500.0 * 8.0 * 1000000 / pacer_->GetPacingRate().ToBps()
      //           << ", seq=" << pkt->GetSeqNum()
      //           << ", retrans=" << pkt->IsRetrans()
      //           << std::endl;
      const TimestampDelta sending_gap = TimestampDelta::FromMicroseconds(
          Packet::MSS * 8.0 * 1000000 / pacer_->GetPacingRate().ToBps());
      if (now - ts_last_burst_sent_end_ > sending_gap) {
        pkt->SetGracePeriod(now - ts_last_burst_sent_end_ - sending_gap);
      } else {
        pkt->SetGracePeriod(now - ts_last_burst_sent_end_);
      }
    }
    if ((!app_->GetPktQueueSizeByte()) && (!rtx_mngr_->GetPktQueueSizeByte())) {
      ts_last_burst_sent_end_ = now;
    }
  }
}

void SalsifyHost::OnPktRcvd(Packet* pkt) {
  if (instanceof <AckPacket>(pkt)) {
    // std::cout << "receive ack pkt" << std::endl;
  } else {
    Timestamp ts_rcvd = pkt->GetTsRcvd();
    if (ts_prev_pkt_rcvd_.ToMicroseconds() != 0) {
      // TODO: figure grace_period
      // TimestampDelta grace_period = pkt->GetTsSent() -
      // pkt->GetTsPrevPktSent();
      TimestampDelta grace_period = pkt->GetGracePeriod();

      // do not compute inter-arrival on 1st rcvd pkt
      TimestampDelta new_tao = std::max(
          TimestampDelta::Zero(), (ts_rcvd - ts_prev_pkt_rcvd_ - grace_period));
      // TimestampDelta new_tao =
      //     std::max(TimestampDelta::Zero(), (ts_rcvd - ts_prev_pkt_rcvd_));
      tao_ = tao_.ToMicroseconds() < 0 ? new_tao
                                       : new_tao * ALPHA + tao_ * (1.0 - ALPHA);
      // std::cout << (ts_rcvd - ts_prev_pkt_rcvd_).ToMicroseconds()
      //           << ", grace=" << grace_period.ToMicroseconds()
      //           << ", new_tao=" << new_tao.ToMicroseconds()
      //           << ", tao=" << tao_.ToMicroseconds() << std::endl;
    }
    ts_prev_pkt_rcvd_ = ts_rcvd;
    SendAck(pkt->GetSeqNum(), pkt->GetTsSent());
  }
}

void SalsifyHost::UpdateRate() {
  const Timestamp& now = Clock::GetClock().Now();
  const auto pacer_update_interval = pacer_->GetUpdateInterval();
  if (now.ToMicroseconds() == 0 ||
      (now - pacer_->GetTsLastPacingRateUpdate()) >= pacer_update_interval) {

    // pace packets out faster
    const double pacing_multiplier = 1.5;
    pacer_->SetPacingRate(cc_->GetEstRate(now, now + pacer_update_interval) *
                          pacing_multiplier);

    // set target bitrate if host is a video sender
    auto video_sender = dynamic_cast<VideoSender*>(app_.get());
    auto salsify = dynamic_cast<Salsify*>(cc_.get());
    if (video_sender && salsify) {
      // allocate rate
      // auto rtx_qsize = rtx_mngr_ ? rtx_mngr_->GetPktQueueSizeByte() * 8 : 0;
      // auto app_qsize = app_->GetPktQueueSizeByte() * 8;
      // auto pacing_rate = pacer_->GetPacingRate();
      // // auto reserved_rate = Rate::FromBps((rtx_qsize + app_qsize) /
      //                                    pacer_update_interval.ToSeconds());
      // auto target_bitrate =
      //     pacing_rate > reserved_rate ? pacing_rate - reserved_rate : Rate();
      auto target_bitrate = salsify->GetEncodeBitrate();
      // std::cout << now.ToMilliseconds()
      //           << ", pacing rate=" << pacing_rate.ToBps()
      //           << ", reserved_rate=" << reserved_rate.ToBps() << ", "
      //           << rtx_qsize << ", " << app_qsize
      //           << ", target bps=" << target_bitrate.ToBps() << std::endl;
      video_sender->SetTargetBitrate(target_bitrate);
    }
  }
}

void SalsifyHost::SendAck(unsigned int seq, const Timestamp& ts_data_pkt_sent) {
  auto& pkt = queue_.emplace_back(std::make_unique<AckPacket>(1));
  auto ack = dynamic_cast<AckPacket*>(pkt.get());
  ack->SetMeanInterarrivalTime(tao_);
  ack->SetAckNum(seq);
  ack->SetTsDataPktSent(ts_data_pkt_sent);
  if (auto vid_rcvr = dynamic_cast<VideoReceiver*>(app_.get()); vid_rcvr) {
    ack->SetLastDecodedFrameId(vid_rcvr->GetLastDecodedFrameId());
  }
}
