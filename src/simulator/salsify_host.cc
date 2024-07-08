#include "salsify_host.h"
#include "utils.h"

SalsifyHost::SalsifyHost(unsigned int id, std::shared_ptr<Link> tx_link,
                         std::shared_ptr<Link> rx_link,
                         std::unique_ptr<Pacer> pacer,
                         std::shared_ptr<CongestionControlInterface> cc,
                         std::unique_ptr<RtxManager> rtx_mngr,
                         std::unique_ptr<ApplicationInterface> app,
                         const std::string& save_dir)
    : Host{id,
           tx_link,
           rx_link,
           std::move(pacer),
           cc,
           std::move(rtx_mngr),
           std::move(app),
           save_dir} {}

void SalsifyHost::OnPktRcvd(std::unique_ptr<Packet> pkt) {

  if (instanceof <AckPacket>(pkt.get())) {
    // std::cout << "receive ack pkt" << std::endl;
  } else {

    Timestamp ts_rcvd = pkt->GetTsRcvd();
    if (ts_prev_pkt_rcvd_.ToMicroseconds() != 0) {
      TimestampDelta grace_period = pkt->GetTsSent() - pkt->GetTsPrevPktSent();

      // do not compute inter-arrival on 1st rcvd pkt
      TimestampDelta new_tao = std::max(
          TimestampDelta::Zero(), (ts_rcvd - ts_prev_pkt_rcvd_ - grace_period));
      tao_ = new_tao * ALPHA + tao_ * (1.0 - ALPHA);
      // std::cout << id_ << " Receive data pkt " << ts_rcvd.ToMicroseconds()
      //           << ", " << ts_prev_pkt_rcvd_.ToMicroseconds() << ", "
      //           << "ts_sent=" << pkt->GetTsSent().ToMicroseconds()
      //           << ", ts_prev_sent=" <<
      //           pkt->GetTsPrevPktSent().ToMicroseconds()
      //           << ", " << grace_period.ToMicroseconds() << ", "
      //           << tao_.ToMicroseconds() << std::endl;
    }
    ts_prev_pkt_rcvd_ = ts_rcvd;
    SendAck(pkt->GetSeqNum(), pkt->GetTsSent());
    app_->DeliverPkt(std::move(pkt));
  }
}

void SalsifyHost::SendAck(unsigned int seq, const Timestamp& ts_data_pkt_sent) {
  auto& pkt = queue_.emplace_back(std::make_unique<AckPacket>(1));
  auto ack = dynamic_cast<AckPacket*>(pkt.get());
  ack->SetMeanInterarrivalTime(tao_);
  ack->SetAckNum(seq);
  ack->SetTsDataPktSent(ts_data_pkt_sent);
}
