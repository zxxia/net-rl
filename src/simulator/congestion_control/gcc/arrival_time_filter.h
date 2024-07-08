#ifndef CONGESTION_CONTROL_GCC_ARRIVAL_TIME_FILTER_H
#define CONGESTION_CONTROL_GCC_ARRIVAL_TIME_FILTER_H

#include "timestamp.h"
#include <deque>

class ArrivalTimeFilter {
public:
  ArrivalTimeFilter() {}

  void AddFrameSentTime(const Timestamp& ts);

  double Update(double delay_gradient);

private:
  static constexpr unsigned int K = 5;
  static constexpr double CHI = 0.1;
  static constexpr double Q = 1e-3;
  double z_ = 0.0;
  double m_hat_ = 0.0;
  double var_v_hat_ = 0.0;
  double e_ = 0.0;
  std::deque<Timestamp> ts_frame_sent_q_;
};
#endif // CONGESTION_CONTROL_GCC_ARRIVAL_TIME_FILTER_H
