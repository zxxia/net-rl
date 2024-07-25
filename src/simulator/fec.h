#ifndef FEC_H
#define FEC_H
#include "application/frame.h"

class FecEncoder {
public:
  FecEncoder() : enabled_(false), rate_(0.0) {}
  inline double GetRate() const { return rate_; }
  inline void Enable() { enabled_ = true; }
  inline void Disable() { enabled_ = false; };
  inline void SetRate(double rate) { rate_ = rate; };
  inline unsigned int Encode(unsigned int fsize_byte) {
    return enabled_ ? fsize_byte / (1.0 - rate_) : fsize_byte;
  }
  inline bool IsEnabled() const { return enabled_; }

private:
  bool enabled_;
  double rate_;
};

class FecDecoder {
public:
  inline void Decode(Frame& frame) {
    frame.frame_size_fec_dec_byte =
        (1.0 - static_cast<double>(frame.frame_size_rcvd_byte) /
                   frame.frame_size_fec_enc_byte) <= frame.fec_rate
            ? frame.frame_size_fec_enc_byte
            : frame.frame_size_rcvd_byte;
  }
};
#endif // FEC_H
