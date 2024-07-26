#include "logger.h"
#include "clock.h"
#include <iostream>

Logger::Logger(const char* log_path)
    : log_path_(log_path), bytes_sent_(0), bytes_rcvd_(0),
      first_pkt_sent_ts_(0), last_pkt_sent_ts_(0), first_pkt_rcvd_ts_(0),
      last_pkt_rcvd_ts_(0),
      stream_(log_path, std::fstream::out | std::fstream::trunc) {

  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
}

void Logger::OnPktSent(const Packet* pkt, const unsigned int tx_link_qsize_byte,
                       const unsigned int rx_link_qsize_byte) {
  const Timestamp& now = Clock::GetClock().Now();
  stream_ << now.ToMicroseconds() << ",-," << pkt->GetSeqNum() << ",,"
          << pkt->GetSizeByte() << ",,," << tx_link_qsize_byte << ","
          << rx_link_qsize_byte << std::endl;
  bytes_sent_ += pkt->GetSizeByte();
  if (first_pkt_sent_ts_.ToMicroseconds() == 0) {
    first_pkt_sent_ts_ = now;
  }
  last_pkt_sent_ts_ = now;
}

void Logger::OnPktRcvd(const Packet* pkt, const unsigned int tx_link_qsize_byte,
                       const unsigned int rx_link_qsize_byte) {
  const Timestamp& now = Clock::GetClock().Now();
  if (auto ack = dynamic_cast<const AckPacket*>(pkt); ack) {
    stream_ << now.ToMicroseconds() << ",+,," << ack->GetAckNum() << ","
            << ack->GetSizeByte() << "," << ack->GetDelayMs() << ","
            << ack->GetRTT().ToMilliseconds() << "," << tx_link_qsize_byte
            << "," << rx_link_qsize_byte << std::endl;
  } else {
    stream_ << now.ToMicroseconds() << ",+," << pkt->GetSeqNum() << ",,"
            << pkt->GetSizeByte() << "," << pkt->GetDelayMs() << ",,"
            << tx_link_qsize_byte << "," << rx_link_qsize_byte << std::endl;
  }
  bytes_rcvd_ += pkt->GetSizeByte();
  if (first_pkt_rcvd_ts_.ToMicroseconds() == 0) {
    first_pkt_rcvd_ts_ = now;
  }
  last_pkt_rcvd_ts_ = now;
}

// void Logger::OnPktLost(const std::unique_ptr<Packet>& pkt) {
//   //const Timestamp& now = Clock::GetClock().Now();
// }

void Logger::Reset() {
  stream_.close();
  stream_.open(log_path_, std::fstream::out | std::fstream::trunc);
  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
  bytes_sent_ = 0;
  bytes_rcvd_ = 0;
  first_pkt_sent_ts_.SetUs(0);
  last_pkt_sent_ts_.SetUs(0);
  first_pkt_rcvd_ts_.SetUs(0);
  last_pkt_rcvd_ts_.SetUs(0);
}

void Logger::Summary() {
  const Timestamp& now = Clock::GetClock().Now();
  TimestampDelta duration = now - Timestamp::Zero();
  double tx_rate_Bps = bytes_sent_ * 1000.0 / duration.ToMilliseconds();
  double rx_rate_Bps = bytes_rcvd_ * 1000.0 / duration.ToMilliseconds();
  std::cout << "\tsending rate: " << tx_rate_Bps << "Bps, "
            << tx_rate_Bps * 8.0 / 1e6 << "Mbps" << std::endl;
  std::cout << "\trecving rate: " << rx_rate_Bps << "Bps, "
            << rx_rate_Bps * 8.0 / 1e6 << "Mbps" << std::endl;
}
