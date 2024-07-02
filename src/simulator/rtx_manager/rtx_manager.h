#ifndef RTX_MANAGER_H
#define RTX_MANAGER_H

#include "clock.h"
#include "congestion_control/congestion_control.h"
#include "packet/packet.h"
#include <set>
#include <unordered_map>

struct RtxInfo {
  unsigned int num_rtx = 0;
  TimestampDelta rto;
  std::unique_ptr<Packet> pkt;
};

class RtxManager : public ClockObserverInterface {
public:
  RtxManager(std::shared_ptr<CongestionControlInterface> cc);
  // virtual void OnPktToSend(Packet *pkt) = 0;

  void Tick() override;
  void Reset() override;
  virtual void OnPktSent(const Packet* pkt);
  virtual void OnPktRcvd(const Packet* pkt);

  // Return the packet size at the front of rtx packet queue.
  virtual unsigned int GetPktToSendSize();

  // Get a packet from the rtx queue.
  virtual std::unique_ptr<Packet> GetPktToSend();

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
#endif // RTX_MANAGER_H
