#ifndef FBRA_H
#define FBRA_H

#include "congestion_control/congestion_control.h"
#include "fec.h"
#include "packet/rtp_packet.h"
#include "rtp_host.h"
#include "timestamp.h"
#include <vector>

class FBRA : public CongestionControlInterface {
public:
  FBRA(std::shared_ptr<FecEncoder>& fec_encoder, const std::string& save_dir);
  void Tick() override;
  void Reset() override;
  void OnPktToSend(Packet*) override{};
  void OnPktSent(const Packet*) override{};
  void OnPktRcvd(const Packet* pkt) override;
  void OnPktLost(const Packet*) override{};
  Rate GetEstRate(const Timestamp&, const Timestamp&) override { return rate_; }

private:
  static constexpr char CSV_HEADER[] =
      "timestamp_us,rate_bps,p40_owd_ms,p80_owd_ms,state,fec_enabled,fec_"
      "interval,corr_owd_low,corr_owd_high";
  static constexpr unsigned int DEACTIVATION_PERIOD_MS =
      1.05 * RTCP_INTERVAL_MS;
  static constexpr double ALPHA_UNDERSHOOT = 2.0;
  static constexpr double ALPHA_STAY = 1.1;
  static constexpr double ALPHA_DOWN = 1.6; // [1.4: 1.6]
  static constexpr double BETA = 1.2;
  static constexpr unsigned int MIN_FEC_INTERVAL = 2;
  static constexpr unsigned int MAX_FEC_INTERVAL = 14;
  static constexpr unsigned int HISTORY_WND_SEC = 2;
  static constexpr unsigned int MIN_RATE_KBPS = 50;

  enum class FBRAState { DOWN, STAY, UP, PROBE };

  void Up(const double recent_losses, const double discards,
          const double corr_owd_high);
  void Down(const double losses, const double discards,
            const double corr_owd_high);
  void Stay(const double losses, const double recent_losses,
            const double recent_discards, const double corr_owd_low,
            const double corr_owd_high);
  void Probe(const double losses, const double recent_losses,
             const double discards, const double recent_discards,
             const double corr_owd_low, const double corr_owd_high);
  void Undershoot();
  void BounceBack();
  void DistableRateControl();

  Rate rate_;
  bool enabled_;
  Timestamp disable_start_ts_;
  FBRAState state_;
  unsigned int fec_interval_;
  std::shared_ptr<FecEncoder> fec_encoder_;
  std::vector<double> owd_history_;
  std::vector<Timestamp> owd_ts_;
  Rate goodput_during_undershoot_;
  RtcpPacket latest_rtcp_;
  std::string save_dir_;
  std::fstream stream_;
};
#endif // FBRA_H
