#include "application/codec.h"
#include "clock.h"
#include <cassert>
#include <climits>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

void LoadLookupTable(const char* lookup_table_path, NvcLookupTable& table) {
  std::string line;
  unsigned int cnt = 0;
  std::ifstream fin(lookup_table_path, std::ios::in);
  while (std::getline(fin, line)) {
    if (cnt == 0) {
      cnt++;
      // skip header
      continue;
    }
    std::stringstream ss(line);
    unsigned int col_cnt = 0, frame_id = 0, model_id = 0;
    FrameStats stats;
    double loss = 0.0;
    while (ss.good()) {
      std::string col;
      getline(ss, col, ',');
      switch (col_cnt) {
      case 0: // size
        stats.emplace("size", std::stod(col));
        break;
      case 1: // psnr
        stats.emplace("psnr", std::stod(col));
        break;
      case 2: // ssim
        stats.emplace("ssim", std::stod(col));
        break;
      case 3: // loss rate
        loss = std::stod(col);
        break;
      case 4: // frame id
        frame_id = std::stoul(col);
        break;
      case 5: // nframes
        break;
      case 6: // model id
        model_id = std::stoul(col);
        break;
      case 7: // video name
        break;
      default:
        break;
      }
      col_cnt++;
    }
    if (frame_id == 0) {
      continue;
    }

    frame_id--;

    if (table.size() >= frame_id + 1) {
      // frame profile of this frame exists
      FrameProfile& frame_profile = table[frame_id];
      if (auto frame_profile_it = frame_profile.find(model_id);
          frame_profile_it == frame_profile.end()) {
        FrameLossProfile loss_profile;
        loss_profile.emplace(loss, stats);
        frame_profile.emplace(model_id, loss_profile);
      } else {
        frame_profile_it->second.emplace(loss, stats);
      }
    } else {
      // frame profile of this frame exists
      FrameProfile frame_profile;
      FrameLossProfile loss_profile;
      loss_profile.emplace(loss, stats);
      frame_profile.emplace(model_id, loss_profile);
      table.push_back(frame_profile);
    }
    cnt++;
  }
  assert(table.size() > 0);
  for (auto i = table.begin(); i != table.end(); i++) {
    assert(i->size() == 11);
    for (auto j = i->begin(); j != i->end(); j++) {
      assert(j->second.size() == 10 || j->second.size() == 1);
      for (auto k = j->second.begin(); k != j->second.end(); k++) {
        assert(k->second.size() == 3);
      }
    }
  }
}

Encoder::Encoder(const std::string& lookup_table_path)
    : encoder_func_(nullptr) {
  LoadLookupTable(lookup_table_path.c_str(), table_);
}

Encoder::Encoder(PyObject* encoder_func) : encoder_func_(encoder_func) {
  assert(PyCallable_Check(encoder_func_));
}

unsigned int Encoder::Encode(unsigned int frame_id,
                             unsigned int target_frame_size_byte,
                             unsigned int& model_id,
                             unsigned int& min_frame_size_byte,
                             unsigned int& max_frame_size_byte) {
  if (!encoder_func_) {
    return EncodeFromLookupTable(frame_id, target_frame_size_byte, model_id,
                                 min_frame_size_byte, max_frame_size_byte);
  }
  return EncodeFromNVC(frame_id, target_frame_size_byte, model_id);
}

unsigned int Encoder::EncodeFromLookupTable(unsigned int frame_id,
                                            unsigned int target_frame_size_byte,
                                            unsigned int& model_id,
                                            unsigned int& min_frame_size_byte,
                                            unsigned int& max_frame_size_byte) {
  int gap0 = INT_MAX, gap1 = INT_MIN, idx = frame_id % table_.size();
  unsigned int model_id0 = 0, model_id1 = 0, fsize0 = 0, fsize1 = 0;
  min_frame_size_byte = table_[idx].at(64).at(0.0).at("size");
  max_frame_size_byte = table_[idx].at(16384).at(0.0).at("size");

  for (const auto& [mid, loss_profile] : table_[idx]) {
    const auto& stats = loss_profile.at(0.0);
    const unsigned int fsize = stats.at("size");
    int tmp_gap =
        static_cast<int>(target_frame_size_byte) - static_cast<int>(fsize);
    if (tmp_gap >= 0 && tmp_gap < gap0) {
      gap0 = tmp_gap;
      model_id0 = mid;
      fsize0 = fsize;
    }
    if (tmp_gap < 0 && tmp_gap > gap1) {
      gap1 = tmp_gap;
      model_id1 = mid;
      fsize1 = fsize;
    }
    // std::cout << mid << ": " << loss_profile.size() << std::endl;
    // std::cout << loss_profile.at(0.0).at("size");
  }
  if (gap0 == INT_MAX) {
    model_id = model_id1;
    return fsize1;
    // return 1500 * 20;
  }
  model_id = model_id0;
  return fsize0;
  // return 1500 * 20;
}

unsigned int Encoder::EncodeFromNVC(unsigned int frame_id,
                                    unsigned int target_frame_size_byte,
                                    unsigned int& model_id) {
  PyObject* args = Py_BuildValue("(ii)", target_frame_size_byte, frame_id);
  PyObject* ret = PyObject_CallObject(encoder_func_, args);
  Py_DECREF(args);
  if (!ret) {
    PyErr_Print();
    throw std::runtime_error("encoder_func error\n");
  }
  // unsigned int fsize = PyLong_AsUnsignedLong(ret);
  PyObject* fsize_ptr = PyTuple_GetItem(ret, 0);
  PyObject* model_id_ptr = PyTuple_GetItem(ret, 1);

  assert(fsize_ptr);
  assert(model_id_ptr);
  unsigned int fsize = PyLong_AsUnsignedLong(fsize_ptr);
  model_id = PyLong_AsUnsignedLong(model_id_ptr);
  // std::cout << PyLong_AsUnsignedLong(model_id_ptr) << std::endl;
  // model_id =
  // std::string(PyString_AsString(model_id_ptr));
  Py_DECREF(ret);
  return fsize;
}

Decoder::Decoder(const std::string& lookup_table_path)
    : decoder_func_(nullptr) {
  LoadLookupTable(lookup_table_path.c_str(), table_);
}

Decoder::Decoder(PyObject* decoder_func) : decoder_func_(decoder_func) {
  assert(PyCallable_Check(decoder_func_));
}

bool Decoder::Decode(Frame& frame, bool is_next_frame_pkt_rcvd) {
  const double loss_rate = frame.GetLossRate();
  const bool can_decode = frame.frame_id == 0
                              ? loss_rate == 0.0
                              : is_next_frame_pkt_rcvd && loss_rate <= 0.9;
  // std::cout << "decode " << can_decode << ", loss " << loss_rate
  //           << ", frame_id " << frame.frame_id << ", " <<
  //           is_next_frame_pkt_rcvd
  //           << ", num_pkt_rcvd=" << frame.num_pkts_rcvd
  //           << ", num_pkt=" << frame.num_pkts
  //           << ", frame_size=" << frame.frame_size_byte
  //           << ", frame_size_rcvd=" << frame.frame_size_rcvd_byte
  //           << ", fec_rate=" << frame.fec_rate
  //           << ", frame_size_fec_enc_byte=" << frame.frame_size_fec_enc_byte
  //           << ", frame_size_fec_dec_byte=" << frame.frame_size_fec_dec_byte
  //           << std::endl;
  if (can_decode) {
    if (!decoder_func_) {
      DecodeFromLookupTable(frame.frame_id, frame.GetLossRate(), frame.model_id,
                            frame.ssim, frame.psnr);
    } else {
      DecodeFromNVC(frame.frame_id, frame.GetLossRate(), frame.model_id,
                    frame.ssim, frame.psnr);
    }
    frame.decode_ts = Clock::GetClock().Now();
  }
  return can_decode;
}

void Decoder::DecodeFromLookupTable(const unsigned int frame_id,
                                    const double loss_rate,
                                    const unsigned int model_id, double& ssim,
                                    double& psnr) {
  const int idx = frame_id % table_.size();
  const double rounded_loss_rate = round(loss_rate * 10.0) / 10.0;
  ssim = table_[idx].at(model_id).at(rounded_loss_rate).at("ssim");
  psnr = table_[idx].at(model_id).at(rounded_loss_rate).at("psnr");
}

void Decoder::DecodeFromNVC(const unsigned int frame_id, const double loss_rate,
                            const unsigned int model_id, double& ssim,
                            double& psnr) {
  (void) model_id;
  PyObject* args = Py_BuildValue("(iii)", frame_id, loss_rate, 1);
  PyObject* ret = PyObject_CallObject(decoder_func_, args);
  Py_DECREF(args);
  if (!ret) {
    PyErr_Print();
    throw std::runtime_error("");
  }
  PyObject* first = PyTuple_GetItem(ret, 0);
  PyObject* second = PyTuple_GetItem(ret, 1);

  psnr = PyFloat_AsDouble(first);
  ssim = PyFloat_AsDouble(second);
  Py_DECREF(ret);
}
