#ifndef RTX_MANAGER_RTP_RTX_MANAGER_H
#define RTX_MANAGER_RTP_RTX_MANAGER_H

#include "rtx_manager/rtx_manager.h"
#include <set>
#include <unordered_map>

class RtpRtxManager : public RtxManagerInterface {
public:
  void Tick() override;
  void Reset() override;
  void OnPktSent(const Packet* pkt) override;
  void OnPktRcvd(const Packet* pkt) override;
  unsigned int GetPktToSendSize() override;
  std::unique_ptr<Packet> GetPktToSend() override;

private:
  std::unordered_map<unsigned int, RtxInfo> buffer_;
  std::set<unsigned int> rtx_queue_;
  Timestamp ts_last_clean_;
};

#endif // RTX_MANAGER_RTP_RTX_MANAGER_H
