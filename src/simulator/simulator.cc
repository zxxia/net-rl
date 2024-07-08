#include "application/file_transfer.h"
#include "application/video_conferencing.h"
#include "clock.h"
#include "congestion_control/fbra.h"
#include "congestion_control/gcc/gcc.h"
#include "congestion_control/oracle_cc.h"
#include "congestion_control/salsify.h"
#include "fec.h"
#include "host.h"
#include "link.h"
#include "pacer.h"
#include "rtp_host.h"
#include "rtx_manager/rtx_manager.h"
#include "salsify_host.h"
#include <cstdlib>
#include <filesystem>
#include <getopt.h>
#include <iostream>
#include <memory>

namespace fs = std::filesystem;

void parse_cmd(int argc, char* argv[], std::string& cc, std::string& trace,
               std::string& lookup_table, std::string& save_dir) {
  int val;

  option longopts[] = {{"cc", required_argument, nullptr, 'c'},
                       {"trace", required_argument, nullptr, 't'},
                       {"lookup-table", required_argument, nullptr, 'l'},
                       {"save-dir", required_argument, nullptr, 'o'},
                       {0, 0, 0, 0}};

  while ((val = getopt_long(argc, argv, "c:t:l:o:", longopts, nullptr)) != -1) {
    switch (val) {
    case 'c':
      cc = std::string(optarg);
      std::cout << "cc=" << cc << std::endl;
      break;
    case 't':
      trace = std::string(optarg);
      std::cout << "trace=" << trace << std::endl;
      break;
    case 'l':
      lookup_table = std::string(optarg);
      std::cout << "look=" << lookup_table << std::endl;
      break;
    case 'o':
      save_dir = std::string(optarg);
      std::cout << "dir=" << save_dir << std::endl;
      break;
    default:
      std::cerr << "unknown arg" << std::endl;
      exit(1);
      break;
    }
  }
}

int main(int argc, char* argv[]) {
  std::string cc;
  std::string trace;
  std::string lookup_table;
  std::string save_dir;
  parse_cmd(argc, argv, cc, trace, lookup_table, save_dir);

  fs::create_directories(save_dir);

  std::srand(42);
  Clock& clk = Clock::GetClock();
  auto tx_link = std::make_shared<Link>(trace.c_str());
  auto rx_link = std::make_shared<Link>(trace.c_str());

  auto fec_encoder = std::make_shared<FecEncoder>();

  // auto app0 = std::make_unique<FileSender>();
  // auto app1 = std::make_unique<FileReceiver>();
  auto app0 = std::make_unique<VideoSender>(lookup_table.c_str(), fec_encoder,
                                            save_dir);
  auto app1 = std::make_unique<VideoReceiver>(lookup_table.c_str(), save_dir);

  auto pacer0 = std::make_unique<Pacer>(1500 * 10, 1);
  auto pacer1 = std::make_unique<Pacer>(1500 * 10, 1);

  std::unique_ptr<RtxManager> rtx_mgnr0;
  std::unique_ptr<RtxManager> rtx_mgnr1;
  std::shared_ptr<CongestionControlInterface> cc0;
  std::shared_ptr<CongestionControlInterface> cc1;
  std::shared_ptr<Host> host0;
  std::shared_ptr<Host> host1;
  if (cc == "fbra" || cc == "FBRA") {
    cc0 = std::make_shared<FBRA>(fec_encoder, save_dir);
    cc1 = std::make_shared<OracleCC>(rx_link);
    rtx_mgnr0 = std::make_unique<RtxManager>(cc0);
    rtx_mgnr1 = std::make_unique<RtxManager>(cc1);
    host0 = std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
                                      std::move(cc0), std::move(rtx_mgnr0),
                                      std::move(app0), save_dir);
    host1 = std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
                                      std::move(cc1), std::move(rtx_mgnr0),
                                      std::move(app1), save_dir);
  } else if (cc == "oracle") {
    cc0 = std::make_unique<OracleCC>(tx_link);
    cc1 = std::make_unique<OracleCC>(rx_link);
    rtx_mgnr0 = std::make_unique<RtxManager>(cc0);
    rtx_mgnr1 = std::make_unique<RtxManager>(cc1);
    host0 = std::make_shared<Host>(0, tx_link, rx_link, std::move(pacer0),
                                   std::move(cc0), std::move(rtx_mgnr0),
                                   std::move(app0), save_dir);
    host1 = std::make_shared<Host>(1, rx_link, tx_link, std::move(pacer1),
                                   std::move(cc1), std::move(rtx_mgnr1),
                                   std::move(app1), save_dir);
  } else if (cc == "salsify") {
    cc0 = std::make_shared<Salsify>(FPS);
    cc1 = std::make_shared<OracleCC>(rx_link);
    rtx_mgnr0 = std::make_unique<RtxManager>(cc0);
    rtx_mgnr1 = nullptr;
    host0 = std::make_shared<SalsifyHost>(
        0, tx_link, rx_link, std::move(pacer0), std::move(cc0),
        std::move(rtx_mgnr0), std::move(app0), save_dir);
    host1 = std::make_shared<SalsifyHost>(
        1, rx_link, tx_link, std::move(pacer1), std::move(cc1),
        std::move(rtx_mgnr1), std::move(app1), save_dir);
  } else if (cc == "gcc" || cc == "GCC") {
    rtx_mgnr0 = nullptr; // std::make_unique<RtxManager>(cc0);
    rtx_mgnr1 = nullptr;
    cc0 = std::make_shared<GCC>();
    cc1 = std::make_shared<GCC>();
    host0 = std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
                                      std::move(cc0), std::move(rtx_mgnr0),
                                      std::move(app0), save_dir);
    host1 = std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
                                      std::move(cc1), std::move(rtx_mgnr1),
                                      std::move(app1), save_dir);
  } else {
    // cc0 = std::make_unique<OracleCC>(tx_link);
    // cc1 = std::make_unique<OracleCC>(rx_link);
    // host0 = std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
    //                                   std::move(cc0), std::move(app0),
    //                                   save_dir);
    // host1 = std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
    //                                   std::move(cc1), std::move(app1),
    //                                   save_dir);
  }

  clk.RegisterObserver(tx_link);
  clk.RegisterObserver(rx_link);
  clk.RegisterObserver(host0);
  clk.RegisterObserver(host1);

  clk.Elapse(30);
  host0->Summary();
  host1->Summary();
  std::cout << "Trace: avg bw=" << tx_link->GetAvgBwMbps() << "Mbps"
            << std::endl;

  return 0;
}
