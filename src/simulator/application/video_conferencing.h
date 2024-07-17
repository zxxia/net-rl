#ifndef VIDEO_CONFERENCING_H
#define VIDEO_CONFERENCING_H
#include "application/application.h"
#include "application/codec.h"
#include "application/frame.h"
#include "fec.h"
#include "rate.h"
#include <deque>
#include <fstream>
#include <unordered_map>

constexpr unsigned int FPS = 25;

class VideoSender : public ApplicationInterface {
public:
  VideoSender(const char* lookup_table_path,
              std::shared_ptr<FecEncoder> fec_encoder,
              const std::string& save_dir);

  unsigned int GetPktToSendSize() const override;

  std::unique_ptr<ApplicationData> GetPktToSend() override;

  void DeliverPkt(std::unique_ptr<Packet>) override{};

  void Tick() override;

  void Reset() override;

  void SetTargetBitrate(const Rate& rate);

  void RegisterTransport(Host*) override {}

  unsigned int GetPktQueueSizeByte() override;

private:
  static constexpr char CSV_HEADER[] =
      "timestamp_us,pacing_rate_bps,fec_data_rate_bps,frame_bitrate_bps,"
      "min_frame_bitrate_bps,max_frame_bitrate_bps,fec_rate";

  void Packetize(const Rate& encode_bitrate, unsigned int frame_size_byte,
                 unsigned int frame_size_fec_enc_byte, unsigned int model_id,
                 double fec_rate, unsigned int padding_byte);

  std::deque<std::unique_ptr<VideoData>> queue_;
  std::deque<std::unique_ptr<VideoData>> padding_queue_;
  Encoder encoder_;
  unsigned int frame_id_;
  Timestamp last_encode_ts_;
  TimestampDelta frame_interval_;
  Rate target_bitrate_;
  std::shared_ptr<FecEncoder> fec_encoder_;
  std::string save_dir_;
  std::fstream stream_;
};

class VideoReceiver : public ApplicationInterface {
public:
  VideoReceiver(const char* lookup_table_path, const std::string& save_dir);

  unsigned int GetPktToSendSize() const override { return 0; }

  std::unique_ptr<ApplicationData> GetPktToSend() override { return nullptr; }

  void DeliverPkt(std::unique_ptr<Packet> pkt) override;

  void Tick() override;

  void Reset() override;

  void RegisterTransport(Host* host) override { host_ = host; }

  unsigned int GetPktQueueSizeByte() override;

private:
  static constexpr char CSV_HEADER[] =
      "frame_id,model_id,frame_encode_ts_us,frame_decode_ts_us,encode_"
      "bitrate_bps,frame_loss_rate,ssim,psnr";
  Decoder decoder_;
  FecDecoder fec_decoder_;
  unsigned int frame_id_;
  Timestamp first_decode_ts_;
  Timestamp last_decode_ts_;
  TimestampDelta frame_interval_;
  std::unordered_map<unsigned int, Frame> queue_;
  std::string save_dir_;
  std::fstream stream_;
  Host* host_;
};
#endif // VIDEO_CONFERENCING_H
