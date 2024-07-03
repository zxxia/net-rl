#ifndef LOGGER_H
#define LOGGER_H

#include "packet/packet.h"
#include <fstream>

class Logger {
public:
  Logger(const char* log_path);

  void OnPktSent(const Packet* pkt);
  void OnPktRcvd(const Packet* pkt);
  // void OnPktLost(const std::unique_ptr<Packet>& pkt);
  void Reset();
  void Summary();

private:
  static constexpr char CSV_HEADER[] =
      "timestamp_us,direction,seq_num,ack_num,pkt_size_byte,one_way_delay_ms,"
      "rtt_ms";
  const char* log_path_;
  unsigned int bytes_sent_;
  unsigned int bytes_rcvd_;
  Timestamp first_pkt_sent_ts_;
  Timestamp last_pkt_sent_ts_;
  Timestamp first_pkt_rcvd_ts_;
  Timestamp last_pkt_rcvd_ts_;
  std::fstream stream_;
};

#endif // LOGGER_H
