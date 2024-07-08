#ifndef CONGESTION_CONTROL_GCC_LOSS_BASED_BWE_H
#define CONGESTION_CONTROL_GCC_LOSS_BASED_BWE_H
#include "rate.h"

class LossBasedBwe {
public:
  LossBasedBwe(const Rate& start_rate) : rate_(start_rate){};
  void OnPktLoss(double loss_fraction) {
    if (loss_fraction > 0.1) {
      rate_ = rate_ * (1 - 0.5 * loss_fraction);
    } else if (loss_fraction < 0.02) {
      rate_ = rate_ * 1.05;
    }
  }

  inline Rate GetRate() const { return rate_; }
  inline void Reset(const Rate& start_rate) { rate_ = start_rate; }

private:
  Rate rate_;
};

#endif // CONGESTION_CONTROL_GCC_LOSS_BASED_BWE_H
