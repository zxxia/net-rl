#ifndef CODEC_H
#define CODEC_H
#include "application/frame.h"
#include <Python.h>
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
  Encoder(const std::string& lookup_table_path);

  Encoder(PyObject* encoder_func);

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

  unsigned int EncodeFromNVC(unsigned int frame_id,
                             unsigned int target_frame_size_byte,
                             unsigned int& model_id);
  NvcLookupTable table_;
  PyObject* encoder_func_;
};

class Decoder {
public:
  Decoder(const std::string& lookup_table_path);

  Decoder(PyObject* decoder_func);

  bool Decode(Frame& frame, bool is_next_frame_pkt_rcvd);

private:
  void DecodeFromLookupTable(const unsigned int frame_id,
                             const double loss_rate,
                             const unsigned int model_id, double& ssim,
                             double& psnr);

  void DecodeFromNVC(const unsigned int frame_id, const double loss_rate,
                     const unsigned int model_id, double& ssim, double& psnr);

  NvcLookupTable table_;
  PyObject* decoder_func_;
};

#endif // CODEC_H
