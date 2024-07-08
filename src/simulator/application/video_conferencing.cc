#include "application/video_conferencing.h"
#include "application/frame.h"
#include "packet/packet.h"
#include "rate.h"
#include "rtp_host.h"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <memory>

VideoSender::VideoSender(const char* lookup_table_path)
    : encoder_(lookup_table_path), frame_id_(0), last_encode_ts_(-1),
      frame_interval_(1000000 / FPS), target_bitrate_(0),
      fec_encoder_(nullptr) {}

VideoSender::VideoSender(const char* lookup_table_path,
                         std::shared_ptr<FecEncoder> fec_encoder)
    : encoder_(lookup_table_path), frame_id_(0), last_encode_ts_(-1),
      frame_interval_(1000000 / FPS), target_bitrate_(0),
      fec_encoder_(fec_encoder),
      stream_("video_sender_log.csv", std::fstream::out | std::fstream::trunc) {

  fec_encoder_->Enable();
  stream_ << "timestamp_us,pacing_rate_bps,fec_data_rate_bps,frame_bitrate_bps,"
             "min_frame_bitrate_bps,max_frame_bitrate_bps,fec_rate"
          << std::endl;
}

unsigned int VideoSender::GetPktToSendSize() const {
  if (queue_.empty()) {
    return 0;
  }
  return queue_.front()->size_byte;
}

std::unique_ptr<ApplicationData> VideoSender::GetPktToSend() {
  auto pkt = std::move(queue_.front());
  queue_.pop_front();
  return pkt;
}

void VideoSender::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  if (last_encode_ts_ < Timestamp::Zero() ||
      (now - last_encode_ts_) >= frame_interval_) {
    // std::cout << target_bitrate_.ToBytePerSec() << std::endl;
    const unsigned int target_data_size_byte =
        target_bitrate_.ToBytePerSec() * frame_interval_.ToSeconds();

    const unsigned int target_fsize_byte =
        fec_encoder_ ? (1.0 - fec_encoder_->GetRate()) * target_data_size_byte
                     : target_data_size_byte;

    unsigned int model_id = 0;
    unsigned int min_frame_size_byte = 0;
    unsigned int max_frame_size_byte = 0;
    const unsigned int fsize_byte =
        encoder_.Encode(frame_id_, target_fsize_byte, model_id,
                        min_frame_size_byte, max_frame_size_byte);

    // fec encode
    const unsigned int fsize_fec_enc_byte =
        fec_encoder_ ? fec_encoder_->Encode(fsize_byte) : fsize_byte;

    // compute padding size
    const unsigned int padding_byte =
        target_data_size_byte > fsize_fec_enc_byte
            ? target_data_size_byte - fsize_fec_enc_byte
            : 0;
    // std::cout << "target data size=" << target_data_size_byte
    //           << ", target_frame_size=" << target_fsize_byte
    //           << ", encoded_frame_size=" << fsize_byte
    //           << ", frame_size_with_fec=" << fsize_with_fec_byte
    //           << ", padding_byte =" << padding_byte << std::endl;
    const unsigned int fec_data_rate =
        8 * (fsize_fec_enc_byte - fsize_byte) / frame_interval_.ToSeconds();
    const unsigned int frame_bitrate =
        8 * fsize_byte / frame_interval_.ToSeconds();
    const unsigned int min_frame_bitrate =
        8 * min_frame_size_byte / frame_interval_.ToSeconds();
    const unsigned int max_frame_bitrate =
        8 * max_frame_size_byte / frame_interval_.ToSeconds();

    const double fec_rate = fec_encoder_ ? fec_encoder_->GetRate() : 0.0;
    const Rate encode_bitrate = target_bitrate_ * (1.0 - fec_rate);
    stream_ << now.ToMicroseconds() << "," << target_bitrate_.ToBps() << ","
            << fec_data_rate << "," << frame_bitrate << "," << min_frame_bitrate
            << "," << max_frame_bitrate << "," << fec_rate << std::endl;
    // packetize encoded video frame and put pkts into application queue
    Packetize(encode_bitrate, fsize_byte, fsize_fec_enc_byte, model_id,
              fec_rate, padding_byte);
    last_encode_ts_ = now;
    ++frame_id_;
  }
}

void VideoSender::Reset() {
  queue_.clear();
  frame_id_ = 0;
  last_encode_ts_.SetUs(-1);
  target_bitrate_.SetBps(0);
  stream_.close();
  stream_.open("video_sender_log.csv", std::fstream::out | std::fstream::trunc);
  stream_ << "timestamp_us,pacing_rate_bps,fec_data_rate_bps,frame_bitrate_bps,"
             "min_frame_bitrate_bps,max_frame_bitrate_bps"
          << std::endl;
}

void VideoSender::SetTargetBitrate(const Rate& rate) { target_bitrate_ = rate; }

void VideoSender::Packetize(const Rate& encode_bitrate,
                            unsigned int frame_size_byte,
                            unsigned int frame_size_fec_enc_byte,
                            unsigned int model_id, double fec_rate,
                            unsigned int padding_byte) {
  // packetize video data
  unsigned int n_pkts = frame_size_fec_enc_byte / Packet::MSS;
  const unsigned int remainder_byte = frame_size_fec_enc_byte % Packet::MSS;
  n_pkts = std::max(n_pkts + static_cast<unsigned int>(remainder_byte > 0), 5u);

  const unsigned int base = frame_size_fec_enc_byte / n_pkts;
  const unsigned int extra = frame_size_fec_enc_byte % n_pkts;
  for (unsigned int i = 0; i < n_pkts; ++i) {
    unsigned int pkt_size = base + (i < extra);
    assert(pkt_size > 0 && pkt_size <= Packet::MSS);
    auto& frame_pkt = queue_.emplace_back(std::make_unique<VideoData>());
    frame_pkt->size_byte = pkt_size;
    frame_pkt->frame_id = frame_id_;
    frame_pkt->model_id = model_id;
    frame_pkt->offset = i;
    frame_pkt->num_pkts = n_pkts;
    frame_pkt->frame_size_byte = frame_size_byte;
    frame_pkt->frame_size_fec_enc_byte = frame_size_fec_enc_byte;
    frame_pkt->encode_ts = Clock::GetClock().Now();
    frame_pkt->encode_bitrate = encode_bitrate;
    frame_pkt->fec_rate = fec_rate;
    frame_pkt->padding_size_byte = padding_byte;
  }

  // packetize padding
  n_pkts = padding_byte / Packet::MSS;
  const unsigned int remainder_padding_byte = padding_byte % Packet::MSS;
  for (unsigned int i = 0; i < n_pkts; ++i) {
    auto& frame_pkt = queue_.emplace_back(std::make_unique<VideoData>());
    frame_pkt->size_byte = Packet::MSS;
    frame_pkt->frame_id = frame_id_;
    frame_pkt->model_id = model_id;
    frame_pkt->num_pkts = n_pkts;
    frame_pkt->frame_size_byte = frame_size_byte;
    frame_pkt->frame_size_fec_enc_byte = frame_size_fec_enc_byte;
    frame_pkt->encode_ts = Clock::GetClock().Now();
    frame_pkt->encode_bitrate = encode_bitrate;
    frame_pkt->fec_rate = fec_rate;

    frame_pkt->padding = true;
    frame_pkt->padding_size_byte = padding_byte;
  }
  if (remainder_padding_byte) {
    auto& frame_pkt = queue_.emplace_back(std::make_unique<VideoData>());
    frame_pkt->size_byte = remainder_padding_byte;
    frame_pkt->frame_id = frame_id_;
    frame_pkt->model_id = model_id;
    frame_pkt->num_pkts = n_pkts;
    frame_pkt->frame_size_byte = frame_size_byte;
    frame_pkt->frame_size_fec_enc_byte = frame_size_fec_enc_byte;
    frame_pkt->encode_ts = Clock::GetClock().Now();
    frame_pkt->encode_bitrate = encode_bitrate;
    frame_pkt->fec_rate = fec_rate;

    frame_pkt->padding = true;
    frame_pkt->padding_size_byte = padding_byte;
  }
}

VideoReceiver::VideoReceiver(const char* lookup_table_path)
    : decoder_(lookup_table_path), frame_id_(0), first_decode_ts_(-1),
      last_decode_ts_(-1), frame_interval_(1000000 / FPS),
      stream_("video_receiver_log.csv",
              std::fstream::out | std::fstream::trunc) {
  stream_ << "frame_id,model_id,frame_encode_ts_us,frame_decode_ts_us,encode_"
             "bitrate_bps,frame_loss_rate,ssim,psnr"
          << std::endl;
}

void VideoReceiver::Tick() {
  const Timestamp& now = Clock::GetClock().Now();
  const auto qend = queue_.end();

  for (auto prev_it = queue_.find(frame_id_ - 1), it = queue_.find(frame_id_),
            next_it = queue_.find(frame_id_ + 1);
       it != qend && // current frame has pkts received
       (frame_id_ == 0 || now - first_decode_ts_ >= frame_interval_);
       ++frame_id_, prev_it = queue_.find(frame_id_ - 1),
            it = queue_.find(frame_id_), next_it = queue_.find(frame_id_ + 1)) {

    auto& frame = it->second;

    fec_decoder_.Decode(frame);

    if (decoder_.Decode(frame, (frame_id_ == 0) || (next_it != qend))) {
      if (auto rtp_host = dynamic_cast<RtpHost*>(host_);
          rtp_host && frame_id_ > 0) {
        assert(prev_it != qend);
        rtp_host->OnFrameRcvd(frame, prev_it->second);
      }
      stream_ << frame_id_ << "," << frame.model_id << ","
              << frame.encode_ts.ToMicroseconds() << ","
              << frame.decode_ts.ToMicroseconds() << ","
              << frame.encode_bitrate.ToBps() << "," << frame.GetLossRate()
              << "," << frame.ssim << "," << frame.psnr << std::endl;
    } else {
      break;
    }
    last_decode_ts_ = now;
    if (first_decode_ts_ < Timestamp::Zero()) {
      first_decode_ts_ = now;
    }
    queue_.erase(frame_id_ - 2);
  }
}

void VideoReceiver::DeliverPkt(std::unique_ptr<Packet> pkt) {
  const auto app_data = pkt->GetApplicationData();
  assert(app_data);
  const auto vid_data = static_cast<const VideoData*>(app_data);

  // Filter out padding packets
  if (vid_data->padding) {
    return;
  }
  // std::cout << pkt->GetSizeByte() << ", " << vid_data.frame_id << ", "
  //           << vid_data.frame_size_byte << "" << std::endl;
  if (auto iter = queue_.find(vid_data->frame_id); iter != queue_.end()) {
    // there are packets for frame_id have arrived already
    auto& frame = iter->second;
    if (frame.pkts_rcvd.find(pkt->GetSeqNum()) != frame.pkts_rcvd.end()) {
      // this pkt was received before, do not take in rtx pkt
      return;
    }
    frame.frame_size_rcvd_byte += pkt->GetSizeByte();
    frame.num_pkts_rcvd++;
    frame.pkts_rcvd.insert(pkt->GetSeqNum());
    frame.last_pkt_sent_ts = pkt->GetTsSent();
    frame.last_pkt_rcvd_ts = pkt->GetTsRcvd();
  } else {
    // no packet for frame_id has arrived yet
    auto res = queue_.emplace(vid_data->frame_id, Frame());
    if (res.second) {
      auto& frame = res.first->second;
      frame.frame_id = vid_data->frame_id;
      frame.model_id = vid_data->model_id;
      frame.first_pkt_seq_num = pkt->GetSeqNum();
      frame.frame_size_byte = vid_data->frame_size_byte;
      frame.frame_size_fec_enc_byte = vid_data->frame_size_fec_enc_byte;
      frame.frame_size_rcvd_byte = pkt->GetSizeByte();
      frame.num_pkts = vid_data->num_pkts;
      frame.num_pkts_rcvd = 1;
      frame.encode_bitrate = vid_data->encode_bitrate;
      frame.encode_ts = vid_data->encode_ts;
      frame.fec_rate = vid_data->fec_rate;
      frame.pkts_rcvd.insert(pkt->GetSeqNum());
      frame.last_pkt_sent_ts = pkt->GetTsSent();
      frame.last_pkt_rcvd_ts = pkt->GetTsRcvd();
      // std::cout << pkt->GetSizeByte() << ", " << frame.frame_id << ", "
      //           << frame.frame_size_byte << "" << std::endl;
    }
  }
}

void VideoReceiver::Reset() {
  frame_id_ = 0;
  first_decode_ts_.SetUs(-1);
  last_decode_ts_.SetUs(-1);
  queue_.clear();
  stream_.close();
  stream_.open("video_receiver_log.csv",
               std::fstream::out | std::fstream::trunc);
}
