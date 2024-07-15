#ifndef RTX_MANAGER_RTX_MANAGER_H
#define RTX_MANAGER_RTX_MANAGER_H

#include "clock.h"
#include "packet/packet.h"


struct RtxInfo {
  unsigned int num_rtx = 0;
  TimestampDelta rto;
  std::unique_ptr<Packet> pkt;
};

class RtxManagerInterface : public ClockObserverInterface {
public:
  virtual void OnPktSent(const Packet* pkt) = 0;
  virtual void OnPktRcvd(const Packet* pkt) = 0;

  // Return the packet size at the front of rtx packet queue.
  virtual unsigned int GetPktToSendSize() = 0;

  // Get a packet from the rtx queue.
  virtual std::unique_ptr<Packet> GetPktToSend() = 0;

  virtual unsigned int GetPktQueueSizeByte() = 0;
};
#endif // RTX_MANAGER_RTX_MANAGER_H
