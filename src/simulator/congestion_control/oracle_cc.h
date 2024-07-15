#ifndef ORACLE_CC_H
#define ORACLE_CC_H

#include "congestion_control/congestion_control.h"
#include "link.h"
#include <memory>

class OracleCC : public CongestionControlInterface {
public:
  OracleCC(std::shared_ptr<Link> link) : link_(link) {}
  void Tick() override {}
  void Reset() override {}

  void OnPktToSend(Packet *) override {}
  void OnPktSent(const Packet *) override {}
  void OnPktRcvd(const Packet *) override {}
  void OnPktLost(const Packet *) override {}
  Rate GetEstRate(const Timestamp & t0, const Timestamp & t1) override {
    return Rate::FromBps(link_->GetAvailBitsToSend(t0, t1) / (t1 - t0).ToSeconds());
  }

private:
  std::shared_ptr<Link> link_;
};

#endif // ORACLE_CC_H
