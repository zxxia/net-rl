#ifndef CONGESTION_CONTROL_H
#define CONGESTION_CONTROL_H

#include "clock.h"
#include "packet/packet.h"
#include "rate.h"
#include "timestamp.h"

class CongestionControlInterface : virtual public ClockObserverInterface {
public:
  virtual void OnPktToSend(Packet *pkt) = 0;
  virtual void OnPktSent(const Packet *pkt) = 0;
  virtual void OnPktRcvd(const Packet *pkt) = 0;
  virtual void OnPktLost(const Packet *pkt) = 0;
  virtual Rate GetEstRate(const Timestamp &start_ts,
                          const Timestamp &end_ts) = 0;
};
#endif // CONGESTION_CONTROL_H
