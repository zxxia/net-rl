#ifndef RTP_HOST_H
#define RTP_HOST_H

#include "application/frame.h"
#include "host.h"
#include "rtx_manager/rtp_rtx_manager.h"
#include <vector>

constexpr unsigned int RTCP_INTERVAL_MS = 50;
constexpr unsigned int REMB_INTERVAL_MS = 1000;

struct RtpState {
  unsigned int max_seq = 0; /* highest seq. number seen */
  // u_int32 cycles;         /* shifted count of seq. number cycles */
  unsigned int base_seq = 0; /* base seq number */
  // u_int32 bad_seq;        /* last 'bad' seq number + 1 */
  // u_int32 probation;      /* sequ. packets till source is valid */
  unsigned int received = 0;       /* packets received */
  unsigned int expected_prior = 0; /* packet expected at last interval */
  unsigned int received_prior = 0; /* packet received at last interval */

  // unsigned int transit;        /* relative trans time for prev pkt */
  // unsigned int jitter;         /* estimated jitter */
  /* ... */
  unsigned int bytes_received = 0;       /* packets received */
  unsigned int bytes_received_prior = 0; /* packet received at last interval */

  TimestampDelta rtt; /* estimated RTT */
};

class NackModule {
public:
  struct NackInfo {
    int retries = 0;
    Timestamp ts_sent;
  };
  void OnPktRcvd(unsigned int seq, unsigned int max_seq);

  void GenerateNacks(std::vector<unsigned int>& nacks, unsigned int max_seq,
                     const TimestampDelta& rtt);

  void OnNackSent(unsigned int seq);

  void CleanUpTo(unsigned int max_seq);

  inline void Reset() { pkts_lost_.clear(); }

private:
  void AddMissing(unsigned int from_seq, unsigned int to_seq);
  std::unordered_map<unsigned int, NackInfo> pkts_lost_;
};

class RtpHost : public Host {
public:
  RtpHost(unsigned int id, std::shared_ptr<Link> tx_link,
          std::shared_ptr<Link> rx_link, std::unique_ptr<Pacer> pacer,
          std::shared_ptr<CongestionControlInterface> cc,
          std::unique_ptr<RtpRtxManager> rtx_mngr,
          std::unique_ptr<ApplicationInterface> app,
          const std::string& save_dir);
  void OnFrameRcvd(const Frame& frame, const Frame& prev_frame);
  void OnPktSent(Packet* pkt) override;
  void OnPktRcvd(Packet* pkt) override;
  std::unique_ptr<Packet> GetPktFromApplication() override;
  void Tick() override;
  void Reset() override;

private:
  void SendRTCPReport(const Rate& remb_rate);
  void SendNacks(std::vector<unsigned int>& nacks);
  Timestamp last_rtcp_report_ts_;
  Timestamp last_remb_ts_;
  RtpState state_;
  unsigned int owd_ms_;

  NackModule nack_module_;
  TimestampDelta sender_rtt_;
};

#endif // RTP_HOST_H
