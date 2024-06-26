#ifndef CODEC_H
#define CODEC_H
#include "application/frame.h"
#include <unordered_map>
#include <vector>

// typedef std::unordered_map<const char *, double> FrameStats;
// typedef std::unordered_map<double, FrameStats> FrameLossProfile;
// typedef std::unordered_map<int, std::vector<FrameLossProfile>>
// NvcLookupTable;

// key: metric name, value: metric value
typedef std::unordered_map<const char*, double> FrameStats;

// key: loss, value: FrameStats
typedef std::unordered_map<double, FrameStats> FrameLossProfile;

// key: model id, value: FrameLossProfile
typedef std::unordered_map<int, FrameLossProfile> FrameProfile;
typedef std::vector<FrameProfile> NvcLookupTable;

class Encoder {
public:
  Encoder(const char* lookup_table_path);
  unsigned int Encode(unsigned int frame_id,
                      unsigned int target_frame_size_byte,
                      unsigned int& model_id, unsigned int& min_frame_size_byte,
                      unsigned int& max_frame_size_byte);

private:
  NvcLookupTable table_;
};

class Decoder {
public:
  Decoder(const char* lookup_table_path);
  bool Decode(Frame& frame, bool is_next_frame_pkt_rcvd);

private:
  NvcLookupTable table_;
};

#endif // CODEC_H
