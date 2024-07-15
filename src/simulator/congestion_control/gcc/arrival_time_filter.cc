#include "congestion_control/gcc/arrival_time_filter.h"
#include <cmath>
#include <limits>

void ArrivalTimeFilter::AddFrameSentTime(const Timestamp& ts) {
  // TODO: check validity of ts
  ts_frame_sent_q_.push_back(ts);
  if (ts_frame_sent_q_.size() > K) {
    ts_frame_sent_q_.pop_front();
  }
}

double ArrivalTimeFilter::Update(double delay_gradient) {
  double f_max = std::numeric_limits<double>::lowest();
  for (unsigned int i = 0; i < ts_frame_sent_q_.size() - 1; ++i) {
    auto tmp = 1000.0 /
               (ts_frame_sent_q_[i + 1] - ts_frame_sent_q_[i]).ToMilliseconds();
    f_max = f_max < tmp ? tmp : f_max;
  }

  double alpha = pow(1.0 - CHI, 30.0 / (1000.0 * f_max));
  z_ = delay_gradient - m_hat_;
  var_v_hat_ = std::max(alpha * var_v_hat_ + (1.0 - alpha) * pow(z_, 2.0), 1.0);
  // z_new = min(self.z, 3 * math.sqrt(self.var_v_hat))
  double z_new = z_;
  double k = (e_ + Q) / (var_v_hat_ + (e_ + Q));
  m_hat_ += z_new * k;
  e_ = (1.0 - k) * (e_ + Q);

  return m_hat_;
}

void ArrivalTimeFilter::Reset() {
  z_ = 0.0;
  m_hat_ = 0.0;
  var_v_hat_ = 0.0;
  e_ = 0.0;
  ts_frame_sent_q_.clear();
}
