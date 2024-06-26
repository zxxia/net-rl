#ifndef APPLICATION_H
#define APPLICATION_H

#include "clock.h"
#include "packet/packet.h"

class ApplicationInterface : virtual public ClockObserverInterface {
public:
  // Return the packet size at the front of application packet queue.
  virtual unsigned int GetPktToSendSize() const = 0;

  // Get a packet from the application to the transport layer.
  virtual std::unique_ptr<ApplicationData> GetPktToSend() = 0;

  // Deliver a packet from the transport layer to the application
  virtual void DeliverPkt(std::unique_ptr<Packet> pkt) = 0;
};
#endif // APPLICATION_H
