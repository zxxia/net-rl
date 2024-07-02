#ifndef TIMESTAMP_H
#define TIMESTAMP_H

class Timestamp;

class TimestampDelta {
public:
  TimestampDelta() : offset_us_(0) {}
  TimestampDelta(int us) : offset_us_(us) {}
  static inline TimestampDelta FromSeconds(int secs) {
    return TimestampDelta(secs * 1000 * 1000);
  }
  static inline TimestampDelta FromMilliseconds(int ms) {
    return TimestampDelta(ms * 1000);
  }
  static inline TimestampDelta FromMicroseconds(int us) {
    return TimestampDelta(us);
  }
  static inline TimestampDelta Zero() { return TimestampDelta(0); }

  inline double ToSeconds() const { return offset_us_ / 1000.0 / 1000.0; }
  inline double ToMilliseconds() const { return offset_us_ / 1000.0; }
  inline int ToMicroseconds() const { return offset_us_; }

  inline bool IsZero() const { return offset_us_ == 0; }

private:
  friend inline bool operator==(const TimestampDelta& lhs,
                                const TimestampDelta& rhs);
  friend inline bool operator!=(const TimestampDelta& lhs,
                                const TimestampDelta& rhs);
  friend inline bool operator<(const TimestampDelta& lhs,
                               const TimestampDelta& rhs);
  friend inline bool operator>(const TimestampDelta& lhs,
                               const TimestampDelta& rhs);
  friend inline bool operator<=(const TimestampDelta& lhs,
                                const TimestampDelta& rhs);
  friend inline bool operator>=(const TimestampDelta& lhs,
                                const TimestampDelta& rhs);
  friend inline TimestampDelta operator+(const TimestampDelta& lhs,
                                         const TimestampDelta& rhs);
  friend inline TimestampDelta operator-(const TimestampDelta& lhs,
                                         const TimestampDelta& rhs);
  friend inline TimestampDelta operator*(const TimestampDelta& lhs,
                                         const int& rhs);
  friend inline TimestampDelta operator*(const TimestampDelta& lhs,
                                         const double& rhs);
  friend inline int operator/(const TimestampDelta& lhs,
                              const TimestampDelta& rhs);
  friend inline Timestamp operator+(const Timestamp& lhs,
                                    const TimestampDelta& rhs);
  friend inline Timestamp operator-(const Timestamp& lhs,
                                    const TimestampDelta& rhs);
  int offset_us_;
  friend class Timestamp;
};

class Timestamp {

public:
  Timestamp() : ts_us_(0) {}
  Timestamp(int ts_us) : ts_us_(ts_us) {}
  static inline Timestamp FromSeconds(int secs) {
    return Timestamp(secs * 1000 * 1000);
  }
  static inline Timestamp FromMilliseconds(int ms) {
    return Timestamp(ms * 1000);
  }
  static inline Timestamp FromMicroseconds(int us) { return Timestamp(us); }
  static inline Timestamp Zero() { return Timestamp(0); }

  inline int ToSeconds() const { return ts_us_ / 1000 / 1000; }
  inline int ToMilliseconds() const { return ts_us_ / 1000; }
  inline int ToMicroseconds() const { return ts_us_; }

  inline void SetUs(int us) { ts_us_ = us; };
  inline void SetMs(int ms) { ts_us_ = ms * 1000; };
  inline void SetSec(int sec) { ts_us_ = sec * 1000 * 1000; };

private:
  friend inline bool operator==(const Timestamp& lhs, const Timestamp& rhs);
  friend inline bool operator!=(const Timestamp& lhs, const Timestamp& rhs);
  friend inline bool operator<(const Timestamp& lhs, const Timestamp& rhs);
  friend inline bool operator>(const Timestamp& lhs, const Timestamp& rhs);
  friend inline bool operator<=(const Timestamp& lhs, const Timestamp& rhs);
  friend inline bool operator>=(const Timestamp& lhs, const Timestamp& rhs);
  friend inline Timestamp operator+(const Timestamp& lhs,
                                    const TimestampDelta& rhs);
  friend inline Timestamp operator-(const Timestamp& lhs,
                                    const TimestampDelta& rhs);
  friend TimestampDelta operator-(const Timestamp& lhs, const Timestamp& rhs);
  int ts_us_;
  friend class TimestampDelta;
};

// Non-member relational operators for TimestampDelta.
inline bool operator==(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ == rhs.offset_us_;
}

inline bool operator!=(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ != rhs.offset_us_;
}

inline bool operator<(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ < rhs.offset_us_;
}

inline bool operator>(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ > rhs.offset_us_;
}

inline bool operator<=(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ <= rhs.offset_us_;
}

inline bool operator>=(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ >= rhs.offset_us_;
}

// Non-member relational operators for Timestamp.
inline bool operator==(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ == rhs.ts_us_;
}

inline bool operator!=(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ != rhs.ts_us_;
}

inline bool operator<(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ < rhs.ts_us_;
}

inline bool operator>(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ > rhs.ts_us_;
}

inline bool operator<=(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ <= rhs.ts_us_;
}

inline bool operator>=(const Timestamp& lhs, const Timestamp& rhs) {
  return lhs.ts_us_ >= rhs.ts_us_;
}

// Non-member arithmatic operators for TimestampDelta.
inline TimestampDelta operator+(const TimestampDelta& lhs,
                                const TimestampDelta& rhs) {
  return TimestampDelta(lhs.offset_us_ + rhs.offset_us_);
}

inline TimestampDelta operator-(const TimestampDelta& lhs,
                                const TimestampDelta& rhs) {
  return TimestampDelta(lhs.offset_us_ - rhs.offset_us_);
}

inline TimestampDelta operator*(const TimestampDelta& lhs, const int& rhs) {
  return TimestampDelta(lhs.offset_us_ * rhs);
}

inline TimestampDelta operator*(const TimestampDelta& lhs, const double& rhs) {
  return TimestampDelta(lhs.offset_us_ * rhs);
}

inline int operator/(const TimestampDelta& lhs, const TimestampDelta& rhs) {
  return lhs.offset_us_ / rhs.offset_us_;
}

// Non-member arithmatic operators for Timestamp and TimestampDelta.
inline Timestamp operator+(const Timestamp& lhs, const TimestampDelta& rhs) {
  return Timestamp(lhs.ts_us_ + rhs.offset_us_);
}

inline Timestamp operator-(const Timestamp& lhs, const TimestampDelta& rhs) {
  return Timestamp(lhs.ts_us_ - rhs.offset_us_);
}

inline TimestampDelta operator-(const Timestamp& lhs, const Timestamp& rhs) {
  return TimestampDelta(lhs.ts_us_ - rhs.ts_us_);
}
#endif // TIMESTAMP_H
