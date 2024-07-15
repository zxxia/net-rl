#include "congestion_control/salsify.h"

Salsify::Salsify(unsigned int fps)
    : rate_(100000), num_pkt_inflight_(0), fps_(fps) {}
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
    // std::cout << "OnPktRcvd " << num_pkt_inflight_ << std::endl;
    num_pkt_inflight_ = std::max(0, num_pkt_inflight_ - 1);
    // update mean_interarrival_time
    const TimestampDelta avg_delay =
        std::max(ack->GetMeanInterarrivalTime(), TimestampDelta(1));

    // TODO: known_receiver_codec_state

    // update estimate rate
    unsigned int max_frame_size_byte =
        Packet::MSS *
        std::max(TimestampDelta::FromMilliseconds(TARGET_E2E_DELAY_CAP_MS) /
                         avg_delay - num_pkt_inflight_,
                 0);
    rate_ = std::max(Rate::FromBytePerSec(max_frame_size_byte * fps_), Rate::FromKbps(MIN_SENDING_RATE_KBPS));
    // std::cout << TimestampDelta::FromMilliseconds(TARGET_E2E_DELAY_CAP_MS) /
    //                      avg_delay << ", inflight=" << num_pkt_inflight_ << ", max_fsize=" << max_frame_size_byte << ", rate = " << rate_.ToMbps()
    //           << "mbps, inter-pkt-delay=" << avg_delay.ToMilliseconds() << "ms"
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
