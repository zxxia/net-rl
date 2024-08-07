#include "link.h"
#include "timestamp.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <sstream>
#include <string>

Link::Link(const char* fname)
    : qsize_byte_(0), last_budget_update_ts_(0), budget_bit_(0) {
  std::string line;
  unsigned int cnt = 0;
  std::ifstream fin(fname, std::ios::in);
  while (std::getline(fin, line)) {
    if (cnt == 0) {
      cnt++;
      // skip header
      continue;
    }
    std::stringstream ss(line);
    unsigned int col_cnt = 0;
    while (ss.good()) {
      std::string col;
      getline(ss, col, ',');
      switch (col_cnt) {
      case 0:
        ts_.emplace_back(1000 * std::stoul(col));
        break;
      case 1:
        bw_mbps_.emplace_back(std::stod(col));
        break;
      case 2:
        if (!col.empty()) {
          prop_delay_ms_ = std::stoul(col);
        }
        break;
      case 3:
        if (!col.empty()) {
          random_loss_rate_ = std::stod(col);
        }
        break;
      case 4:
        if (!col.empty()) {
          qcap_byte_ = std::stoul(col);
        }
        break;
      case 5:
        // TODO: T_s
        break;
      default:
        break;
      }
      col_cnt++;
    }
    cnt++;
  }
}

double Link::GetAvgBwMbps() const {
  if (bw_mbps_.empty()) {
    return 0.0;
  }
  auto const count = static_cast<double>(bw_mbps_.size());
  return std::reduce(bw_mbps_.cbegin(), bw_mbps_.cend()) / count;
}

void Link::Push(std::unique_ptr<Packet> pkt) {
  const unsigned int pkt_size = pkt->GetSizeByte();
  // drop pkt if random packet loss or queue is full
  // queue capacity is inifite if capacity equals to unsigned int max
  if (static_cast<double>(rand()) / RAND_MAX > random_loss_rate_ &&
      (qcap_byte_ == std::numeric_limits<unsigned int>::max() ||
       pkt_size + qsize_byte_ <= qcap_byte_)) {
    pkt->AddPropDelayMs(prop_delay_ms_);
    queue_.push_back(std::move(pkt));
    qsize_byte_ += pkt_size;
  } else {
    // std::cout << "drop " << pkt->GetSeqNum() << std::endl;
  }
}

std::unique_ptr<Packet> Link::Pull() {
  // Pull a packet from the link
  // check pkt timestamp to determine whether to dequeue a pkt
  if (!ready_pkts_.empty()) {
    std::unique_ptr<Packet>& pkt = ready_pkts_.front();
    const Timestamp& now = Clock::GetClock().Now();
    if (pkt->GetTsSent() +
            TimestampDelta::FromMilliseconds(pkt->GetDelayMs()) <=
        now) {
      auto ret = std::move(ready_pkts_.front());
      ready_pkts_.pop_front();
      return ret;
    }
  }
  return std::unique_ptr<Packet>(nullptr);
}

void Link::Tick() { UpdateBwBudget(); }

void Link::Reset() {
  qsize_byte_ = 0;
  budget_bit_ = 0;
  last_budget_update_ts_.SetUs(0);
  queue_.clear();
  ready_pkts_.clear();
}

unsigned int Link::GetAvailBitsToSend(const Timestamp& t0,
                                      const Timestamp& t1) const {
  const TimestampDelta step = ts_.at(1) - ts_.at(0);
  const Timestamp ts_start = ts_.at(0);
  const int start = ((t0 - ts_start) / step) % ts_.size();
  const int end = ((t1 - ts_start) / step) % ts_.size();
  double bits = 0.0;
  if (start > end) {
    bits =
        std::accumulate(bw_mbps_.cbegin() + start, bw_mbps_.cend(), 0.0) *
            step.ToMicroseconds() +
        std::accumulate(bw_mbps_.cbegin(), bw_mbps_.cbegin() + end + 1, 0.0) *
            step.ToMicroseconds();
  } else {
    bits = std::accumulate(bw_mbps_.cbegin() + start,
                           bw_mbps_.cbegin() + end + 1, 0.0) *
           step.ToMicroseconds();
  }
  bits -= bw_mbps_.at(start) *
          (t0 - (Timestamp::Zero() + step * start)).ToMicroseconds();
  bits -= bw_mbps_.at(end) *
          ((Timestamp::Zero() + step * (end + 1)) - t1).ToMicroseconds();
  // std::cout << "now=" << Clock::GetClock().Now().ToMicroseconds()
  //           << ", ts_start=" << ts_start.ToMicroseconds()
  //           << ", t0=" << t0.ToMicroseconds()
  //           << ", start=" << start //(step * start).ToMicroseconds()
  //           << ", bin start=" << (Timestamp::Zero() + step *
  //           start).ToMicroseconds()
  //           << ", t1=" << t1.ToMicroseconds()
  //           << ", bin end=" << (Timestamp::Zero() + step *
  //           end).ToMicroseconds()
  //           << ", end=" << end // (step * end).ToMicroseconds()
  //           << ", step=" << step.ToMicroseconds()
  //           << ", bits=" << bits
  //           << ", buget_bits=" << budget_bit_
  //           << ", qlen=" << queue_.size()
  //           << std::endl;
  return bits;
}

void Link::UpdateBwBudget() {
  const Timestamp& now = Clock::GetClock().Now();

  while (!queue_.empty()) {
    std::unique_ptr<Packet>& pkt = queue_.front();
    Timestamp ts_sent = pkt->GetTsSent();
    Timestamp prev_ts = std::max(ts_sent, last_budget_update_ts_);
    const unsigned int pkt_size = pkt->GetSizeByte();
    const auto bits = GetAvailBitsToSend(prev_ts, now);
    budget_bit_ = prev_ts == ts_sent ? bits : budget_bit_ + bits;
    last_budget_update_ts_ = now;
    if (budget_bit_ >= (pkt_size * 8)) {
      budget_bit_ -= (pkt_size * 8);
      pkt->AddQueueDelayMs((now - ts_sent).ToMilliseconds());
      qsize_byte_ -= pkt_size;
      ready_pkts_.push_back(std::move(pkt));
      queue_.pop_front();
    } else {
      break;
    }
  }
}
