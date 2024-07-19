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
#include "rtx_manager/ack_based_rtx_manager.h"
#include "rtx_manager/rtp_rtx_manager.h"
#include "salsify_host.h"
#include <cstdlib>
#include <filesystem>
#include <getopt.h>
#include <iostream>
#include <memory>

namespace fs = std::filesystem;

#define OPTIONAL_ARGUMENT_IS_PRESENT                                           \
  ((optarg == NULL && optind < argc && argv[optind][0] != '-')                 \
       ? (bool)(optarg = argv[optind++])                                       \
       : (optarg != NULL))

void parse_cmd(int argc, char* argv[], std::string& cc, std::string& trace,
               std::string& lookup_table, std::string& save_dir,
               std::string& video_path) {
  int val;
  option longopts[] = {{"cc", required_argument, nullptr, 'c'},
                       {"trace", required_argument, nullptr, 't'},
                       {"lookup-table", optional_argument, nullptr, 'l'},
                       {"save-dir", required_argument, nullptr, 'o'},
                       {"video", optional_argument, nullptr, 'v'},
                       {0, 0, 0, 0}};

  while ((val = getopt_long(argc, argv, "c:t:l::o:v::", longopts, nullptr)) !=
         -1) {
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
      if (OPTIONAL_ARGUMENT_IS_PRESENT) {
        lookup_table = std::string(optarg);
        std::cout << "lookup table=" << lookup_table << std::endl;
      }
      break;
    case 'o':
      save_dir = std::string(optarg);
      std::cout << "dir=" << save_dir << std::endl;
      break;
    case 'v':
      if (OPTIONAL_ARGUMENT_IS_PRESENT) {
        video_path = std::string(optarg);
        std::cout << "video path=" << video_path << std::endl;
      }
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
  std::string video_path;
  parse_cmd(argc, argv, cc, trace, lookup_table, save_dir, video_path);

  assert(fs::exists(lookup_table) || fs::exists(video_path));

  fs::create_directories(save_dir);

  std::srand(42);
  Clock& clk = Clock::GetClock();
  auto tx_link = std::make_shared<Link>(trace.c_str());
  auto rx_link = std::make_shared<Link>(trace.c_str());

  auto fec_encoder = std::make_shared<FecEncoder>();

  auto app0 = std::make_unique<VideoSender>(lookup_table, video_path,
                                            fec_encoder, save_dir);
  auto app1 =
      std::make_unique<VideoReceiver>(lookup_table, video_path, save_dir);

  auto pacer0 = std::make_unique<Pacer>(1500 * 10, 40);
  auto pacer1 = std::make_unique<Pacer>(1500 * 10, 1);

  std::shared_ptr<Host> host0;
  std::shared_ptr<Host> host1;
  if (cc == "fbra" || cc == "FBRA") {
    auto cc0 = std::make_shared<FBRA>(fec_encoder, save_dir);
    auto cc1 = std::make_shared<OracleCC>(rx_link);
    std::unique_ptr<RtpRtxManager> rtx_mgnr0 =
        std::make_unique<RtpRtxManager>();
    std::unique_ptr<RtpRtxManager> rtx_mgnr1 = nullptr;
    host0 = std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
                                      std::move(cc0), std::move(rtx_mgnr0),
                                      std::move(app0), save_dir);
    host1 = std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
                                      std::move(cc1), std::move(rtx_mgnr0),
                                      std::move(app1), save_dir);
  } else if (cc == "oracle") {
    auto cc0 = std::make_unique<OracleCC>(tx_link);
    auto cc1 = std::make_unique<OracleCC>(rx_link);
    std::unique_ptr<RtxManagerInterface> rtx_mgnr0 = nullptr;
    std::unique_ptr<RtxManagerInterface> rtx_mgnr1 = nullptr;
    host0 = std::make_shared<Host>(0, tx_link, rx_link, std::move(pacer0),
                                   std::move(cc0), std::move(rtx_mgnr0),
                                   std::move(app0), save_dir);
    host1 = std::make_shared<Host>(1, rx_link, tx_link, std::move(pacer1),
                                   std::move(cc1), std::move(rtx_mgnr1),
                                   std::move(app1), save_dir);
  } else if (cc == "salsify") {
    auto cc0 = std::make_shared<Salsify>(FPS);
    auto cc1 = std::make_shared<OracleCC>(rx_link);
    std::unique_ptr<AckBasedRtxManager> rtx_mgnr0 =
        std::make_unique<AckBasedRtxManager>(cc0);
    std::unique_ptr<AckBasedRtxManager> rtx_mgnr1 = nullptr;
    host0 = std::make_shared<SalsifyHost>(
        0, tx_link, rx_link, std::move(pacer0), std::move(cc0),
        std::move(rtx_mgnr0), std::move(app0), save_dir);
    host1 = std::make_shared<SalsifyHost>(
        1, rx_link, tx_link, std::move(pacer1), std::move(cc1),
        std::move(rtx_mgnr1), std::move(app1), save_dir);
  } else if (cc == "gcc" || cc == "GCC") {
    std::unique_ptr<RtpRtxManager> rtx_mgnr0 =
        std::make_unique<RtpRtxManager>();
    std::unique_ptr<RtpRtxManager> rtx_mgnr1 = nullptr;
    auto cc0 = std::make_shared<GCC>(0, save_dir);
    auto cc1 = std::make_shared<GCC>(1, save_dir);
    host0 = std::make_shared<RtpHost>(0, tx_link, rx_link, std::move(pacer0),
                                      std::move(cc0), std::move(rtx_mgnr0),
                                      std::move(app0), save_dir);
    host1 = std::make_shared<RtpHost>(1, rx_link, tx_link, std::move(pacer1),
                                      std::move(cc1), std::move(rtx_mgnr1),
                                      std::move(app1), save_dir);
  } else {
    std::cerr << cc << " is not supported." << std::endl;
    return 1;
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
