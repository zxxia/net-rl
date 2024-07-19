#ifndef CODEC_H
#define CODEC_H
#include "application/frame.h"
#include <string>
#include <unordered_map>
#include <vector>

// key: metric name, value: metric value
typedef std::unordered_map<const char*, double> FrameStats;

// key: loss, value: FrameStats
typedef std::unordered_map<double, FrameStats> FrameLossProfile;

// key: model id, value: FrameLossProfile
typedef std::unordered_map<int, FrameLossProfile> FrameProfile;
typedef std::vector<FrameProfile> NvcLookupTable;

class Encoder {
public:
  Encoder(const std::string& lookup_table_path, const std::string& video_path,
          const std::string& save_dir);
  unsigned int Encode(unsigned int frame_id,
                      unsigned int target_frame_size_byte,
                      unsigned int& model_id, unsigned int& min_frame_size_byte,
                      unsigned int& max_frame_size_byte);

private:
  unsigned int EncodeFromLookupTable(unsigned int frame_id,
                                     unsigned int target_frame_size_byte,
                                     unsigned int& model_id,
                                     unsigned int& min_frame_size_byte,
                                     unsigned int& max_frame_size_byte);

  unsigned int EncodeFromVideo(unsigned int frame_id,
                               unsigned int target_frame_size_byte,
                               unsigned int& model_id,
                               unsigned int& min_frame_size_byte,
                               unsigned int& max_frame_size_byte);
  NvcLookupTable table_;
  std::string video_path_;
  std::string save_dir_;
};

class Decoder {
public:
  Decoder(const std::string& lookup_table_path, const std::string& video_path,
          const std::string& save_dir);
  bool Decode(Frame& frame, bool is_next_frame_pkt_rcvd);

private:
  bool DecodeFromLookupTable(Frame& frame, bool is_next_frame_pkt_rcvd);
  bool DecodeFromVideo(Frame& frame, bool is_next_frame_pkt_rcvd);

  NvcLookupTable table_;
  std::string video_path_;
  std::string save_dir_;
};

#endif // CODEC_H
