#include "congestion_control/fbra.h"
#include "utils.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <vector>

namespace fs = std::filesystem;

FBRA::FBRA(std::shared_ptr<FecEncoder>& fec_encoder,
           const std::string& save_dir)
    : rate_(100000), enabled_(true), state_{FBRAState::STAY}, fec_interval_(8),
      fec_encoder_(fec_encoder), save_dir_(save_dir) {
  fec_encoder_->SetRate(1.0 / fec_interval_);
  fec_encoder_->Disable();

  fs::create_directories(save_dir_);
  fs::path dir(save_dir_);
  fs::path file("fbra_log.csv");
  stream_.open((dir / file).c_str(), std::fstream::out | std::fstream::trunc);
  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
}

void FBRA::Tick() {
  if (!enabled_ && disable_start_ts_.ToMicroseconds() != 0 &&
      (latest_rtcp_.GetTsRcvd() - disable_start_ts_) >=
          TimestampDelta::FromMilliseconds(DEACTIVATION_PERIOD_MS)) {
    BounceBack();
  }
}

void FBRA::Reset() {
  rate_ = Rate::FromBps(100000);
  enabled_ = true;
  disable_start_ts_.SetUs(0);
  state_ = FBRAState::STAY;
  fec_interval_ = 8;
  owd_history_.clear();
  owd_ts_.clear();
  goodput_during_undershoot_ = Rate::FromBps(0);
  stream_.close();
  fs::path dir(save_dir_);
  fs::path file("fbra_log.csv");
  stream_.open((dir / file).c_str(), std::fstream::out | std::fstream::trunc);
  assert(stream_.is_open());
  stream_ << CSV_HEADER << std::endl;
}

void FBRA::OnPktRcvd(const Packet* pkt) {
  const auto& now = Clock::GetClock().Now();
  if (auto rtcp_pkt = dynamic_cast<const RtcpPacket*>(pkt);
      rtcp_pkt != nullptr) {
    latest_rtcp_ = *rtcp_pkt;

    const auto owd_ms = rtcp_pkt->GetOwd();
    if (owd_ms == 0) {
      return;
    }
    const auto losses = rtcp_pkt->GetLossFraction();
    const auto goodput = rtcp_pkt->GetTput();
    if (losses == 0.0 || owd_history_.empty()) {
      owd_history_.emplace_back(static_cast<double>(owd_ms));
      owd_ts_.emplace_back(now);
      while ((!owd_ts_.empty()) &&
             (now - owd_ts_.front()) >
                 TimestampDelta::FromSeconds(HISTORY_WND_SEC)) {
        owd_history_.erase(owd_history_.begin());
        owd_ts_.erase(owd_ts_.begin());
      }
    }
    if (!enabled_ && disable_start_ts_.ToMicroseconds() != 0 &&
        (now - disable_start_ts_) <
            TimestampDelta::FromMilliseconds(DEACTIVATION_PERIOD_MS)) {
      goodput_during_undershoot_ = goodput;
    }

    const auto p40_owd = percentile(owd_history_, 40.0);
    const auto p80_owd = percentile(owd_history_, 80.0);
    const auto corr_owd_low = owd_ms / p40_owd;
    const auto corr_owd_high = owd_ms / p80_owd;
    stream_ << now.ToMicroseconds() << "," << rate_.ToBps() << "," << p40_owd
            << "," << p80_owd << "," << static_cast<int>(state_) << ","
            << fec_encoder_->IsEnabled() << "," << fec_interval_ << ","
            << corr_owd_low << "," << corr_owd_high << std::endl;
    if (!enabled_) {
      return;
    }

    switch (state_) {
    case FBRAState::UP:
      Up(losses, 0.0, corr_owd_high);
      break;
    case FBRAState::DOWN:
      Down(losses, 0.0, corr_owd_high);
      break;
    case FBRAState::STAY:
      Stay(losses, losses, 0.0, corr_owd_low, corr_owd_high);
      break;
    case FBRAState::PROBE:
      Probe(losses, losses, 0.0, 0.0, corr_owd_low, corr_owd_high);
      break;
    default:
      break;
    }

  } else if (auto rtp_pkt = dynamic_cast<const RtpPacket*>(pkt);
             rtp_pkt != nullptr) {
  }
}

void FBRA::Up(const double recent_losses, const double discards,
              const double corr_owd_high) {
  if (recent_losses || discards || corr_owd_high > ALPHA_DOWN) {
    Undershoot();
    DistableRateControl();
    state_ = FBRAState::DOWN;
  } else {
    state_ = FBRAState::STAY;
    fec_encoder_->Disable();
  }
}

void FBRA::Down(const double losses, const double discards,
                const double corr_owd_high) {
  if (losses || discards) {
    if (state_ == FBRAState::DOWN) {
      state_ = FBRAState::STAY;
    } else {
      if (discards && losses == 0) {
        Undershoot();
      } else {
        Undershoot();
        DistableRateControl();
        state_ = FBRAState::DOWN;
      }
    }
  } else if (corr_owd_high > ALPHA_UNDERSHOOT) {
    Undershoot();
    DistableRateControl();
    state_ = FBRAState::DOWN;
  } else {
    state_ = FBRAState::STAY;
  }
  fec_encoder_->Disable();
}

void FBRA::Stay(const double losses, const double recent_losses,
                const double recent_discards, const double corr_owd_low,
                const double corr_owd_high) {
  if (losses) {
    if (recent_losses) {
      Undershoot();
      DistableRateControl();
      state_ = FBRAState::DOWN;
    } else {
      state_ = FBRAState::STAY;
    }
    fec_encoder_->Disable();
  } else {
    if (recent_discards) {
      Undershoot();
      DistableRateControl();
      fec_encoder_->Disable();
      state_ = FBRAState::DOWN;
    } else {
      if (corr_owd_high > ALPHA_STAY) {
        if (state_ == FBRAState::STAY) {
          Undershoot();
          DistableRateControl();
          state_ = FBRAState::DOWN;
        } else {
          state_ = FBRAState::STAY;
        }
        fec_encoder_->Disable();
      } else {

        // Decrement fec interval starts (added by zxxia)
        if (corr_owd_low <= 1.0 && corr_owd_high <= 1.0) {
          fec_interval_ = std::max(
              MIN_FEC_INTERVAL, std::min(fec_interval_ - 1, MAX_FEC_INTERVAL));
          fec_encoder_->SetRate(1.0 / fec_interval_);
        }
        // Decrement fec interval ends (added by zxxia)
        state_ = FBRAState::PROBE;
        fec_encoder_->Enable();
      }
    }
  }
}
void FBRA::Probe(const double losses, const double recent_losses,
                 const double discards, const double recent_discards,
                 const double corr_owd_low, const double corr_owd_high) {
  if (recent_losses || recent_discards) {
    Undershoot();
    DistableRateControl();
    fec_encoder_->Disable();
    state_ = FBRAState::DOWN;
  } else if (losses || discards) {
    state_ = FBRAState::STAY;
    fec_encoder_->Disable();
  } else {
    if (corr_owd_high > ALPHA_DOWN) {
      Undershoot();
      DistableRateControl();
      fec_encoder_->Disable();
      state_ = FBRAState::DOWN;
    } else if (corr_owd_high > ALPHA_STAY) {
      state_ = FBRAState::STAY;
      fec_encoder_->Disable();
    } else if (corr_owd_low > BETA) {
      // increment fec interval to reduce redundancy
      fec_interval_ = std::max(MIN_FEC_INTERVAL,
                               std::min(fec_interval_ + 1, MAX_FEC_INTERVAL));
      // set fec rate
      fec_encoder_->SetRate(1.0 / fec_interval_);
      state_ = FBRAState::PROBE;
    } else {
      state_ = FBRAState::UP;
      rate_ = std::min(std::max(rate_ * (1.0 / (1.0 - fec_encoder_->GetRate())),
                                Rate::FromKbps(MIN_RATE_KBPS)),
                       Rate::FromKbps(MAX_RATE_KBPS));
      fec_encoder_->Disable();
    }
  }
}

void FBRA::DistableRateControl() {
  enabled_ = false;
  disable_start_ts_ = Clock::GetClock().Now();
}

void FBRA::Undershoot() {
  // std::cout <<Clock::GetClock().Now().ToSeconds() << " 2*(rate-goodput)=" <<
  // ((rate_-goodput)*1.0).ToMbps() <<" undershoot rate " << rate_.ToMbps() << "
  // to ";

  // paper default undershoot logic
  // rate_ = rate_ - (rate_ - goodput) * 1.0;
  // rate_ = rate_ * 0.9;
  // std::cout << rate_.ToMbps() << " to ";
  // std::cout << rate_.ToMbps() << std::endl;
  rate_ = std::min(std::max(rate_ * 0.85, Rate::FromKbps(MIN_RATE_KBPS)),
                   Rate::FromKbps(MAX_RATE_KBPS));
}

void FBRA::BounceBack() {
  if (latest_rtcp_.GetLossFraction()) {
    // Undershoot(latest_rtcp_.GetTput());
    Undershoot();
  } else {
    // std::cout <<Clock::GetClock().Now().ToSeconds() << " bounce rate " <<
    // rate_.ToMbps() << " to ";
    // std::cout << rate_.ToMbps() << std::endl;
    rate_ = std::min(std::max(goodput_during_undershoot_ * 0.9,
                              Rate::FromKbps(MIN_RATE_KBPS)),
                     Rate::FromKbps(MAX_RATE_KBPS));
  }
  state_ = FBRAState::STAY;
  enabled_ = true;
}
