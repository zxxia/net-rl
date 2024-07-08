#include "congestion_control/gcc/delay_based_bwe.h"
#include "clock.h"
#include <cmath>
#include <numeric>

DelayBasedBwe::DelayBasedBwe(const Rate& start_rate)
    : rcv_rate_(0), delay_grad_thresh_ms_(START_DELAY_GRADIENT_THRESH_MS),
      delay_grad_ms_(0.0), delay_grad_hat_ms_(0.0), sig_(BwUsageSignal::NORMAL),
      new_sig_(BwUsageSignal::NORMAL), ts_overuse_start_(0),
      state_(RateControlState::INC), rate_update_ts_(0), rate_(start_rate) {}

void DelayBasedBwe::OnPktRcvd(const RtpPacket* pkt) {
  pkt_size_wnd_.emplace_back(pkt->GetSizeByte());
  ts_rcvd_wnd_.emplace_back(pkt->GetTsRcvd());
}

void DelayBasedBwe::OnFrameRcvd(const Timestamp& ts_frame_sent,
                                const Timestamp& ts_frame_rcvd,
                                const Timestamp& ts_prev_frame_sent,
                                const Timestamp& ts_prev_frame_rcvd) {
  const Timestamp& now = Clock::GetClock().Now();
  TimestampDelta wnd_dur = TimestampDelta::FromMilliseconds(HISTORY_WINDOW_MS);
  unsigned int i = 0;
  while (i < ts_rcvd_wnd_.size()) {
    if (now - ts_rcvd_wnd_[i] > wnd_dur) {
      ++i;
    } else {
      break;
    }
  }
  ts_rcvd_wnd_.erase(ts_rcvd_wnd_.begin(), ts_rcvd_wnd_.begin() + i);
  pkt_size_wnd_.erase(pkt_size_wnd_.begin(), pkt_size_wnd_.begin() + i);

  wnd_dur =
      now - Timestamp::Zero() < wnd_dur ? now - Timestamp::Zero() : wnd_dur;
  rcv_rate_ = Rate::FromBps(
      8.0 * std::accumulate(pkt_size_wnd_.cbegin(), pkt_size_wnd_.cend(), 0) /
      wnd_dur.ToSeconds());

  // add frame send time to arrival time filter
  filter_.AddFrameSentTime(ts_frame_sent);

  // compute delay gradient
  delay_grad_ms_ = ((ts_frame_rcvd - ts_prev_frame_rcvd) -
                    (ts_frame_sent - ts_prev_frame_sent))
                       .ToMilliseconds();

  // feed gradient to filter
  delay_grad_hat_ms_ = filter_.Update(delay_grad_ms_);

  // adjust delay gradient threshold
  double k_gamma = fabs(delay_grad_hat_ms_) < delay_grad_thresh_ms_ ? K_D : K_U;
  delay_grad_thresh_ms_ +=
      (ts_frame_rcvd - ts_prev_frame_rcvd).ToMilliseconds() * k_gamma *
      (fabs(delay_grad_hat_ms_) - delay_grad_thresh_ms_);

  // generate new signal
  UpdateBwOveruseSignal();

  // update state
  UpdateState();

  // update est rate
  UpdateRate();

  // std::cout << "delay_bwe=" << rate_.ToMbps() << ", state=" << static_cast<int>(state_)
  //           << ", d_hat=" << delay_grad_hat_ms_ << std::endl;

  // TODO: send report
}

void DelayBasedBwe::UpdateState() {
  switch (state_) {
  case RateControlState::DEC:
    if (sig_ != BwUsageSignal::OVERUSE) {
      state_ = RateControlState::HOLD;
    }
    break;
  case RateControlState::HOLD:
    if (sig_ == BwUsageSignal::OVERUSE) {
      state_ = RateControlState::DEC;
    } else if (sig_ == BwUsageSignal::NORMAL) {
      state_ = RateControlState::INC;
    }
    break;
  case RateControlState::INC:
    if (sig_ == BwUsageSignal::OVERUSE) {
      state_ = RateControlState::DEC;
    } else if (sig_ == BwUsageSignal::UNDERUSE) {
      state_ = RateControlState::HOLD;
    }
    break;
  default:
    break;
  }
}

void DelayBasedBwe::UpdateBwOveruseSignal() {

  const Timestamp& now = Clock::GetClock().Now();
  auto new_sig = BwUsageSignal::NORMAL;
  if (delay_grad_hat_ms_ > delay_grad_thresh_ms_) {
    new_sig = BwUsageSignal::OVERUSE;
  } else if (delay_grad_hat_ms_ < (-1) * delay_grad_thresh_ms_) {
    new_sig = BwUsageSignal::UNDERUSE;
  } else {
    new_sig = BwUsageSignal::NORMAL;
  }

  if (new_sig == BwUsageSignal::OVERUSE) {
    if (new_sig != sig_) {
      if (new_sig != new_sig_) {
        new_sig_ = new_sig;
        ts_overuse_start_ = now;
      } else if (now - ts_overuse_start_ >= OVERUSE_THRESH_MS) {
        sig_ = new_sig_;
      }
    }
  } else {
    new_sig_ = new_sig;
    sig_ = new_sig;
  }
}

void DelayBasedBwe::UpdateRate() {
  const Timestamp& now = Clock::GetClock().Now();
  switch (state_) {
  case RateControlState::INC:
    rate_ = std::min(
        rate_ * pow(ETA, std::min((now - rate_update_ts_).ToSeconds(), 1.0)),
        rcv_rate_ * 1.5);
    break;
  case RateControlState::DEC:
    rate_ = std::min(rcv_rate_ * ALPHA, rcv_rate_ * 1.5);
    break;
  case RateControlState::HOLD:
    rate_ = std::min(rate_, rcv_rate_ * 1.5);
    break;
  default:
    break;
  }
  rate_update_ts_ = now;
}
