#ifndef PACKET_H
#define PACKET_H
#include "rate.h"
#include "timestamp.h"
#include <memory>

struct ApplicationData {
  unsigned int size_byte;
  virtual ~ApplicationData() {}
  virtual ApplicationData* Clone() const { return new ApplicationData(*this); }
};

/**
 * Application-layer video frame data carried by a packet
 */
struct VideoData : public ApplicationData {
  unsigned int frame_id = 0;
  unsigned int model_id = 0;
  unsigned int offset = 0; // pkt idx within a sequence of packets for a frame
  unsigned int num_pkts = 0;
  unsigned int frame_size_byte = 0;
  unsigned int frame_size_fec_enc_byte = 0;
  Timestamp encode_ts;
  Rate encode_bitrate;
  double fec_rate = 0.0;
  bool padding = false;
  unsigned int padding_size_byte = 0;
  virtual VideoData* Clone() const { return new VideoData(*this); }
};

class Packet {
public:
  static constexpr unsigned int MSS = 1500;

  Packet(unsigned int size_byte)
      : size_byte_(size_byte), seq_num_(0), prop_delay_ms_(0),
        queue_delay_ms_(0), ts_sent_(0), ts_first_sent_(0),
        ts_prev_pkt_sent_(0), ts_rcvd_(0), app_data_{nullptr} {}

  Packet(std::unique_ptr<ApplicationData> app_data)
      : seq_num_(0), prop_delay_ms_(0), queue_delay_ms_(0), ts_sent_(0),
        ts_first_sent_(0), ts_prev_pkt_sent_(0), ts_rcvd_(0),
        app_data_{std::move(app_data)} {
    size_byte_ = app_data_ ? app_data_->size_byte : 0;
  }

  Packet(const Packet& other) {
    if (this != &other) {
      size_byte_ = other.size_byte_;
      seq_num_ = other.seq_num_;
      prop_delay_ms_ = other.prop_delay_ms_;
      queue_delay_ms_ = other.queue_delay_ms_;

      ts_sent_ = other.ts_sent_;
      ts_first_sent_ = other.ts_first_sent_;
      ts_prev_pkt_sent_ = other.ts_prev_pkt_sent_;
      ts_rcvd_ = other.ts_rcvd_;
      app_data_ =
          other.app_data_
              ? std::unique_ptr<ApplicationData>(other.app_data_->Clone())
              : nullptr;
    }
  }

  Packet& operator=(const Packet& other) {
    if (this != &other) { // Self-assignment check
      size_byte_ = other.size_byte_;
      seq_num_ = other.seq_num_;
      prop_delay_ms_ = other.prop_delay_ms_;
      queue_delay_ms_ = other.queue_delay_ms_;

      ts_sent_ = other.ts_sent_;
      ts_first_sent_ = other.ts_first_sent_;
      ts_prev_pkt_sent_ = other.ts_prev_pkt_sent_;
      ts_rcvd_ = other.ts_rcvd_;

      // payload for application
      if (other.app_data_) {
        app_data_.reset(other.app_data_->Clone());
      }
    }
    return *this;
  }
  virtual ~Packet() = default;
  // Accessors
  inline unsigned int GetSizeByte() const { return size_byte_; }
  inline Timestamp GetTsSent() const { return ts_sent_; }
  inline Timestamp GetTsRcvd() const { return ts_rcvd_; }
  inline Timestamp GetTsFirstSent() const { return ts_first_sent_; }
  inline Timestamp GetTsPrevPktSent() const { return ts_prev_pkt_sent_; }
  inline unsigned int GetDelayMs() const {
    return prop_delay_ms_ + queue_delay_ms_;
  }
  inline unsigned int GetSeqNum() const { return seq_num_; }
  inline const ApplicationData* GetApplicationData() const {
    if (app_data_)
      return app_data_.get();
    return nullptr;
  }
  inline TimestampDelta GetGracePeriod() const { return grace_period_; }
  inline bool IsRetrans() const { return ts_sent_ != ts_first_sent_; }

  inline void AddQueueDelayMs(unsigned int delay_ms) {
    queue_delay_ms_ += delay_ms;
  }
  inline void AddPropDelayMs(unsigned int delay_ms) {
    prop_delay_ms_ += delay_ms;
  }
  inline void SetSeqNum(unsigned int seq_num) { seq_num_ = seq_num; }
  inline void SetTsRcvd(const Timestamp& ts) { ts_rcvd_ = ts; }
  inline void SetTsSent(const Timestamp& ts) {
    ts_sent_ = ts;
    if (ts_first_sent_.ToMicroseconds() == 0) {
      ts_first_sent_ = ts;
    }
  }
  inline void SetTsPrevPktSent(const Timestamp& ts) { ts_prev_pkt_sent_ = ts; }

  inline void SetGracePeriod(const TimestampDelta& grace_period) {
    grace_period_ = grace_period;
  }

protected:
  unsigned int size_byte_;
  unsigned int seq_num_;
  unsigned int prop_delay_ms_;
  unsigned int queue_delay_ms_;

  Timestamp ts_sent_;
  Timestamp ts_first_sent_;
  Timestamp ts_prev_pkt_sent_;
  Timestamp ts_rcvd_;

  TimestampDelta grace_period_; // for salsify

  // payload for application
  std::unique_ptr<ApplicationData> app_data_;
};

class AckPacket : public Packet {
public:
  AckPacket(unsigned int size_byte, unsigned int data_pkt_size_byte)
      : Packet(size_byte), data_pkt_size_(data_pkt_size_byte) {}

  inline unsigned int GetAckNum() const { return ack_num_; }

  inline TimestampDelta GetMeanInterarrivalTime() const {
    return mean_interarrival_time_;
  }

  inline TimestampDelta GetRTT() const { return ts_rcvd_ - ts_data_pkt_sent_; }

  inline int GetLastDecodedFrameId() const { return last_decoded_frame_id_; }

  inline unsigned int GetDataPktSize() const { return data_pkt_size_; }

  inline void SetAckNum(unsigned int ack_num) { ack_num_ = ack_num; }

  inline void SetMeanInterarrivalTime(const TimestampDelta& interarrival_time) {
    mean_interarrival_time_ = interarrival_time;
  }

  inline void SetTsDataPktSent(const Timestamp& ts) { ts_data_pkt_sent_ = ts; }

  inline void SetLastDecodedFrameId(int frame_id) {
    last_decoded_frame_id_ = frame_id;
  }

private:
  unsigned int ack_num_;       // seq no. of the corresponding data pkt
  Timestamp ts_data_pkt_sent_; // sent time of the corresponding data pkt
  unsigned int data_pkt_size_; // size of the corresponding data pkt in byte
  TimestampDelta mean_interarrival_time_;
  int last_decoded_frame_id_;
  // codec state
};
#endif // PACKET_H
