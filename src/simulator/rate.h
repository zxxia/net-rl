#ifndef RATE_H
#define RATE_H
#include <iostream>
#include <cassert>

class Rate {
public:
  Rate(unsigned int bps) : bps_(bps) {}
  Rate() : bps_(0) {}
  static inline Rate FromBytePerSec(unsigned int byte_per_sec) {
    return Rate(byte_per_sec * 8);
  }
  static inline Rate FromBps(unsigned int bps) { return Rate(bps); }
  static inline Rate FromKbps(double kbps) { return Rate(kbps * 1000); }
  static inline Rate FromMbps(double mbps) { return Rate(mbps * 1000 * 1000); }

  inline double ToBytePerSec() const { return bps_ / 8.0; }
  inline unsigned int ToBps() const { return bps_; }
  inline double ToKbps() const { return bps_ / 1000.0; }
  inline double ToMbps() const { return bps_ / 1000.0 / 1000.0; }

  inline void SetBps(unsigned int bps) { bps_ = bps; }

private:
  friend inline bool operator==(const Rate &lhs, const Rate &rhs);
  friend inline bool operator!=(const Rate &lhs, const Rate &rhs);
  friend inline bool operator<(const Rate &lhs, const Rate &rhs);
  friend inline bool operator>(const Rate &lhs, const Rate &rhs);
  friend inline bool operator<=(const Rate &lhs, const Rate &rhs);
  friend inline bool operator>=(const Rate &lhs, const Rate &rhs);
  friend inline double operator/(const Rate &lhs, const Rate &rhs);
  friend inline Rate operator*(const Rate &lhs, const double &rhs);
  friend inline Rate operator+(const Rate &lhs, const Rate &rhs);
  friend inline Rate operator-(const Rate &lhs, const Rate &rhs);

  unsigned int bps_;
};

// Non-member relational operators for Rate.
inline bool operator==(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ == rhs.bps_;
}

inline bool operator!=(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ != rhs.bps_;
}

inline bool operator<(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ < rhs.bps_;
}

inline bool operator>(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ > rhs.bps_;
}

inline bool operator<=(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ <= rhs.bps_;
}

inline bool operator>=(const Rate &lhs, const Rate &rhs) {
  return lhs.bps_ >= rhs.bps_;
}

inline Rate operator+(const Rate &lhs, const Rate &rhs) {
  return Rate(lhs.bps_ + rhs.bps_);
}

inline Rate operator-(const Rate &lhs, const Rate &rhs) {
  std::cerr << lhs.bps_ << " - " << rhs.bps_ << std::endl;
  assert(lhs.bps_ >= rhs.bps_);
  return Rate(lhs.bps_ - rhs.bps_);
}

inline double operator/(const Rate &lhs, const Rate &rhs) {
  return static_cast<double>(lhs.bps_) / rhs.bps_;
}

inline Rate operator*(const Rate &lhs, const double &rhs) {
  //std::cout << lhs.bps_ << ", "<< rhs << std::endl;
  return Rate(lhs.bps_ * rhs);
}
#endif // RATE_H
