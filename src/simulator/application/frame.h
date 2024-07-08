#ifndef FRAME_H
#define FRAME_H
#include "packet/packet.h"
#include "rate.h"
#include "timestamp.h"
#include <set>

/**
 * Frame received by a video receiver.
 */
struct Frame {
  unsigned int frame_id = 0;
  unsigned int model_id = 0;
  unsigned int first_pkt_seq_num = 0;
  unsigned int frame_size_byte = 0; // actual frame size before fec encoding
  unsigned int frame_size_fec_enc_byte = 0; // frame size after fec encoding

  // bytes received (padding bytes are not inclueded)
  unsigned int frame_size_rcvd_byte = 0;

  // bytes received and then fec decoded (padding bytes are not inclueded)
  unsigned int frame_size_fec_dec_byte = 0;
  unsigned int num_pkts = 0;
  unsigned int num_pkts_rcvd = 0;
  Rate encode_bitrate;
  Timestamp encode_ts;
  Timestamp decode_ts;
  Timestamp last_pkt_sent_ts;
  Timestamp last_pkt_rcvd_ts;
  double fec_rate = 0.0;
  //"padding_bytes": 0, "num_padding_pkts_rcvd": 0,
  std::set<unsigned int> pkts_rcvd;

  // metrics after frame decode
  double ssim = -1.0;
  double psnr = -1.0;

  inline TimestampDelta GetFrameDelay() const { return decode_ts - encode_ts; }

  inline double GetLossRate() const {
    if (frame_size_fec_dec_byte && frame_size_fec_enc_byte)  // after fec decode
      return 1.0 - static_cast<double>(frame_size_fec_dec_byte) / frame_size_fec_enc_byte;
    else if (frame_size_fec_enc_byte) // before fec decode
      return 1.0 - static_cast<double>(frame_size_rcvd_byte) / frame_size_fec_enc_byte;
    else if (frame_size_byte) { // if no fec used at all
      return 1.0 - static_cast<double>(frame_size_rcvd_byte) / frame_size_byte;
    }
    // meaningless loss rate
    return -1.0;
  };
};

#endif // FRAME_H
