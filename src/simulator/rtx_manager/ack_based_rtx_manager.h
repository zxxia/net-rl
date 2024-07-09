#ifndef RTX_MANAGER_ACK_BASED_RTX_MANAGER_H
#define RTX_MANAGER_ACK_BASED_RTX_MANAGER_H

#include "congestion_control/congestion_control.h"
#include "packet/packet.h"
#include "rtx_manager/rtx_manager.h"
#include <set>
#include <unordered_map>

class AckBasedRtxManager : public RtxManagerInterface {
public:
  AckBasedRtxManager(std::shared_ptr<CongestionControlInterface> cc);

  void Tick() override;
  void Reset() override;
  void OnPktSent(const Packet* pkt) override;
  void OnPktRcvd(const Packet* pkt) override;
  unsigned int GetPktToSendSize() override;
  std::unique_ptr<Packet> GetPktToSend() override;

private:
  static constexpr double SRTT_ALPHA = 1.0 / 8;
  static constexpr double SRTT_BETA = 1.0 / 4;
  static constexpr double RTO_K = 4;

  void UpdateRTO(const AckPacket& ack);

  std::unordered_map<unsigned int, RtxInfo> buffer_;
  std::set<unsigned int> rtx_queue_;
  std::shared_ptr<CongestionControlInterface> cc_;
  int max_ack_num_;

  TimestampDelta srtt_;
  TimestampDelta rttvar_;
  TimestampDelta rto_;
};
#endif // RTX_MANAGER_ACK_BASED_RTX_MANAGER_H
