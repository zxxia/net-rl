#ifndef UTILS_H
#define UTILS_H

#include <algorithm> // for std::sort
#include <iostream>
#include <numeric>
#include <vector>

template <typename Base, typename T> inline bool instanceof (const T* ptr) {
  return dynamic_cast<const Base*>(ptr) != nullptr;
}

// Function to calculate the percentile of a vector
inline double percentile(const std::vector<double>& data, double p) {
  if (data.empty()) {
    throw std::invalid_argument(
        "Cannot calculate percentile of an empty vector");
  }

  // Step 1: Sort the vector
  std::vector<double> sortedData = data;
  std::sort(sortedData.begin(), sortedData.end());

  // Step 2: Calculate the position
  double n = sortedData.size();
  double position = p / 100.0 * (n - 1); // position starts from 0

  // Step 3: Interpolate if necessary
  if (position <= 0.0) {
    return sortedData[0];
  } else if (position >= n - 1) {
    return sortedData[n - 1];
  } else {
    double lower = sortedData[static_cast<int>(position)];
    double upper = sortedData[static_cast<int>(position) + 1];
    return lower + (position - static_cast<int>(position)) * (upper - lower);
  }
}

// Calculate the mean of a vector
inline double mean(const std::vector<double>& data) {
  if (data.empty()) {
    throw std::invalid_argument(
        "Cannot calculate percentile of an empty vector");
  }
  return std::accumulate(data.cbegin(), data.cend(), 0.0) / data.size();
}
#endif // UTILS_H
