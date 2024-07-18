#include "congestion_control/salsify.h"
// #include <iostream>
Salsify::Salsify(unsigned int fps)
    : rate_(100000), encode_bitrate_(100000), num_pkt_inflight_(0), fps_(fps) {}
Salsify::Salsify() : rate_(100000), num_pkt_inflight_(0), fps_(0) {}

void Salsify::Tick() {}

void Salsify::Reset() {
  rate_ = Rate::FromBps(100000);
  num_pkt_inflight_ = 0;
}

void Salsify::OnPktSent(const Packet*) {
  // std::cout << "OnPktSent " << num_pkt_inflight_ << std::endl;
  num_pkt_inflight_++;
};

void Salsify::OnPktRcvd(const Packet* pkt) {
  if (auto ack = dynamic_cast<const AckPacket*>(pkt); ack != nullptr) {
    num_pkt_inflight_ = std::max(0, num_pkt_inflight_ - 1);
    // std::cout << "avg_inter_arrival_t " <<
    // ack->GetMeanInterarrivalTime().ToMicroseconds() << std::endl;

    // get mean_interarrival_time
    TimestampDelta avg_delay = ack->GetMeanInterarrivalTime();
    if (avg_delay.ToMicroseconds() < 0) {
      return;
    }
    avg_delay = std::max(avg_delay, TimestampDelta(1));

    // TODO: known_receiver_codec_state
    const Rate incoming_rate =
        Rate::FromBytePerSec(Packet::MSS / avg_delay.ToSeconds());

    // update estimate rate
    const unsigned int max_frame_size_byte =
        Packet::MSS *
        std::max(TARGET_E2E_DELAY_CAP_MS / avg_delay.ToMilliseconds() -
                     num_pkt_inflight_,
                 0.0);

    rate_ = incoming_rate;
    encode_bitrate_ = std::max(Rate::FromBytePerSec(max_frame_size_byte * fps_),
                               Rate::FromKbps(MIN_RATE_KBPS));
    // std::cout << Clock::GetClock().Now().ToMilliseconds() << ", ratio="
    //           << TimestampDelta::FromMilliseconds(TARGET_E2E_DELAY_CAP_MS) /
    //                  avg_delay
    //           << ", inflight=" << num_pkt_inflight_
    //           << ", max_fsize=" << max_frame_size_byte
    //           << ", rate = " << rate_.ToMbps()
    //           << ", encode rate = " << encode_bitrate.ToMbps()
    //           << "mbps, inter-pkt-delay=" << avg_delay.ToMilliseconds()
    //           << "ms, incoming_rate=" << incoming_rate.ToMbps() << "mbps"
    //           << std::endl;
  } else { // data packet
  }
}

void Salsify::OnPktLost(const Packet*) {
  // std::cout << "OnPktLost " << num_pkt_inflight_ << std::endl;
  num_pkt_inflight_ = std::max(0, num_pkt_inflight_ - 1);
  // TODO:
  /*if (ack indicate loss) {
    enter loss recovery mode for next 5 seconds
  }*/
};
