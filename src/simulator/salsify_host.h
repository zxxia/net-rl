#ifndef SALSIFY_HOST_H
#define SALSIFY_HOST_H
#include "host.h"
#include "rtx_manager/ack_based_rtx_manager.h"

class SalsifyHost : public Host {
public:
  SalsifyHost(unsigned int id, std::shared_ptr<Link> tx_link,
              std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
              std::shared_ptr<CongestionControlInterface> cc,
              std::unique_ptr<AckBasedRtxManager> rtx_mngr,
              std::unique_ptr<ApplicationInterface> app,
              const std::string& save_dir);
  void OnPktRcvd(std::unique_ptr<Packet> pkt) override;
  TimestampDelta GetMeanInterarrivalTime() const { return tao_; }

private:
  static constexpr double ALPHA = 0.1;

  void SendAck(unsigned int seq, const Timestamp& ts_data_pkt_sent);

  // receiver-side variables
  TimestampDelta tao_; // smoothed inter-arrival time
  Timestamp ts_prev_pkt_rcvd_;
};
#endif // SALSIFY_HOST_H
