#include "application/file_transfer.h"
#include "application/video_conferencing.h"
#include "clock.h"
#include "congestion_control/fbra.h"
#include "congestion_control/oracle_cc.h"
#include "fec.h"
#include "host.h"
#include "link.h"
#include "logger.h"
#include "pacer.h"
#include "rtp_host.h"
#include <cstdlib>
#include <iostream>
#include <memory>

int main() {
  std::srand(42);
  Clock &clk = Clock::GetClock();
  auto logger0 = std::make_shared<Logger>("./pkt_log0.csv");
  auto logger1 = std::make_shared<Logger>("./pkt_log1.csv");
  auto tx_link = std::make_shared<Link>("../../const_trace.csv");
  auto rx_link = std::make_shared<Link>("../../const_trace.csv");
  auto fec_encoder = std::make_shared<FecEncoder>();
  // auto cc0 = std::make_unique<OracleCC>(tx_link);
  auto cc1 = std::make_unique<OracleCC>(rx_link);
  auto cc0 = std::make_unique<FBRA>(fec_encoder);
  auto pacer0 = std::make_unique<Pacer>(1500 * 10, 1);
  auto pacer1 = std::make_unique<Pacer>(1500 * 10, 1);

  // auto app0 = std::make_unique<FileSender>();
  // auto app1 = std::make_unique<FileReceiver>();
  auto app0 = std::make_unique<VideoSender>(
      "../../data/AE_lookup_table/segment_0vu1_dwHF7g_480x360.mp4.csv",
      fec_encoder);
  auto app1 = std::make_unique<VideoReceiver>(
      "../../data/AE_lookup_table/segment_0vu1_dwHF7g_480x360.mp4.csv");
  auto host0 =
      std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
                                std::move(cc0), std::move(app0), logger0);
  auto host1 =
      std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
                                std::move(cc1), std::move(app1), logger1);
  clk.RegisterObserver(tx_link);
  clk.RegisterObserver(rx_link);
  clk.RegisterObserver(host0);
  clk.RegisterObserver(host1);

  clk.Elapse(30);
  std::cout << "Host 0" << std::endl;
  logger0->Summary();
  std::cout << "Host 1" << std::endl;
  logger1->Summary();
  std::cout << "Trace: avg bw=" << tx_link->GetAvgBwMbps() << "Mbps"
            << std::endl;

  return 0;
}
