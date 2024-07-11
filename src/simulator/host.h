#ifndef HOST_H
#define HOST_H
#include "application/application.h"
#include "clock.h"
#include "congestion_control/congestion_control.h"
#include "link.h"
#include "logger.h"
#include "pacer.h"
#include "rtx_manager/rtx_manager.h"
#include "timestamp.h"
#include <memory>

class Host : public ClockObserverInterface {
public:
  // pass unique_ptr by value
  Host(unsigned int id, std::shared_ptr<Link> tx_link,
       std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
       std::shared_ptr<CongestionControlInterface> cc,
       std::unique_ptr<RtxManagerInterface> rtx_mngr,
       std::unique_ptr<ApplicationInterface> app, const std::string& save_dir);
  void Tick() override;
  void Reset() override;
  void Summary();

protected:
  virtual void OnPktRcvd(Packet*) {}
  virtual void OnPktSent(Packet*) {}
  virtual std::unique_ptr<Packet> GetPktFromApplication();
  void Send();
  void Receive();
  unsigned int GetPktToSendSize() const;
  std::unique_ptr<Packet> GetPktToSend();
  void UpdateRate();

  unsigned int id_;
  std::shared_ptr<Link> tx_link_;
  std::shared_ptr<Link> rx_link_;
  std::unique_ptr<Pacer> pacer_;
  std::shared_ptr<CongestionControlInterface> cc_;
  std::unique_ptr<RtxManagerInterface> rtx_mngr_;
  std::unique_ptr<ApplicationInterface> app_;
  unsigned int seq_num_;
  std::deque<std::unique_ptr<Packet>> queue_;
  Timestamp ts_pkt_sent_;
  Logger logger_;
};

#endif // HOST_H
