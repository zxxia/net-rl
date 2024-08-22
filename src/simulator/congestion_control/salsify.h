#ifndef CONGESTION_CONTROL_SALSIFY_H
#define CONGESTION_CONTROL_SALSIFY_H

#include "congestion_control/congestion_control.h"
#include <fstream>

class Salsify : public CongestionControlInterface {
public:
  Salsify(unsigned int fps, const std::string& save_dir);
  void Tick() override;
  void Reset() override;

  void OnPktToSend(Packet*) override {}
  void OnPktSent(const Packet*) override;
  void OnPktRcvd(const Packet* pkt) override;
  void OnPktLost(const Packet*) override;
  Rate GetEstRate(const Timestamp&, const Timestamp&) override { return rate_; }
  Rate GetEncodeBitrate() { return encode_bitrate_; }

private:
  static constexpr char CSV_HEADER[] =
      "timestamp_us,num_pkt_inflight,avg_inter_pkt_delay_ms,incoming_rate_bps,"
      "encode_bitrate_bps";
  static constexpr unsigned int TARGET_E2E_DELAY_CAP_MS = 100;
  static constexpr unsigned int MIN_RATE_KBPS = 50;
  static constexpr unsigned int MAX_RATE_KBPS = 24000;

  void InitLog();

  // sender-side variables
  Rate rate_;
  Rate encode_bitrate_;
  int num_pkt_inflight_;
  unsigned int fps_;
  std::string save_dir_;
  std::fstream stream_;
};
#endif // CONGESTION_CONTROL_SALSIFY_H
