#ifndef PACKET_RTP_PACKET_H
#define PACKET_RTP_PACKET_H

#include "packet/packet.h"
class RtpPacket : public Packet {
public:
  RtpPacket(unsigned int size_byte) : Packet{size_byte} {}
  RtpPacket(std::unique_ptr<ApplicationData> app_data)
      : Packet{std::move(app_data)} {}

  RtpPacket(const RtpPacket& other) : Packet(other) {
    if (this != &other) {
      rtt_ = other.rtt_;
    }
  }
  inline const TimestampDelta GetRTT() const { return rtt_; }
  inline void SetRTT(const TimestampDelta& rtt) { rtt_ = rtt; }

private:
  TimestampDelta rtt_;
};

class RtcpPacket : public Packet {
public:
  RtcpPacket() : Packet{0}, loss_fraction_(0.0){};
  RtcpPacket(unsigned int size_byte, double loss_fraction)
      : Packet{size_byte}, loss_fraction_(loss_fraction){};

  // Default copy assignment operator (compiler-provided)
  RtcpPacket& operator=(const RtcpPacket& other) {
    if (this != &other) { // Self-assignment check
      Packet::operator=(other);
      // Copy data from 'other' to 'this'
      loss_fraction_ = other.loss_fraction_;
      owd_ms_ = other.owd_ms_; // Copy data from 'other' to 'this'
      tput_ = other.tput_;     // Copy data from 'other' to 'this'
    }
    return *this;
  }

  inline double GetLossFraction() const { return loss_fraction_; }
  // inline const std::vector<unsigned int> &GetOwd() const { return owd_ms_; }
  // inline void LoadOwd(std::vector<unsigned int> &owd) { owd_ms_.swap(owd); }
  inline unsigned int GetOwd() const { return owd_ms_; }
  inline const Rate GetTput() const { return tput_; }
  inline const Rate GetRembRate() const { return remb_rate_; }
  inline int GetLastDecodedFrameId() const { return last_decoded_frame_id_; }

  inline void SetOwd(unsigned int owd) { owd_ms_ = owd; }
  inline void SetTput(const Rate& tput) { tput_ = tput; }
  inline void SetRembRate(const Rate& rate) { remb_rate_ = rate; }
  inline void SetLastDecodedFrameId(int frame_id) {
    last_decoded_frame_id_ = frame_id;
  }

private:
  double loss_fraction_;
  // std::vector<unsigned int> owd_ms_;
  unsigned int owd_ms_;
  Rate tput_;
  Rate remb_rate_;
  int last_decoded_frame_id_;
};

class RtpNackPacket : public Packet {
public:
  RtpNackPacket(unsigned int nack_num) : Packet{1}, nack_num_(nack_num){};

  inline unsigned int GetNackNum() const { return nack_num_; }

private:
  unsigned int nack_num_;
};
#endif // PACKET_RTP_PACKET_H
