#define PY_SSIZE_T_CLEAN
#include <Python.h>

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

struct PyInterpreter {

  PyInterpreter() {}

  ~PyInterpreter() {
    if (Py_IsInitialized()) {
      Py_FinalizeEx();
    }
  }

  void Init() {
    Py_Initialize();
    PyRun_SimpleString("import sys,os\nsys.path.append(os.getcwd())");
  }
};

struct PyModule {
  PyObject* module = nullptr;
  const char* m_name = nullptr;

  PyModule(const char* name) { m_name = name; }

  ~PyModule() {
    if (module) {
      Py_DECREF(module);
    }
  }

  void Import() {
    PyObject* module_name = PyUnicode_DecodeFSDefault(m_name);
    if (!module_name) {
      throw std::runtime_error("Cannot decode module name.");
    }
    module = PyImport_Import(module_name);
    if (!module) {
      Py_DECREF(module_name);
      throw std::runtime_error("Python import module failed.");
    }
    Py_DECREF(module_name);
  }

  PyObject* GetAttr(const char* name) {
    PyObject* attr = PyObject_GetAttrString(module, name);
    if (!attr) {
      if (module) {
        Py_DECREF(module);
      }
      PyErr_Print();
      throw std::runtime_error("Get attribute failed.");
    }
    return attr;
  }
};

int main(int argc, char* argv[]) {
  std::string cc, trace, lookup_table, save_dir, video_path;
  parse_cmd(argc, argv, cc, trace, lookup_table, save_dir, video_path);

  assert(fs::exists(lookup_table) || fs::exists(video_path));

  fs::create_directories(save_dir);
  PyObject* encoder_func = nullptr;
  PyObject* decoder_func = nullptr;
  PyObject* on_decoder_feedback_func = nullptr;
  PyInterpreter interpreter;
  PyModule module("grace-gpu");

  std::srand(42);
  Clock& clk = Clock::GetClock();
  auto tx_link = std::make_shared<Link>(trace.c_str());
  auto rx_link = std::make_shared<Link>(trace.c_str());

  auto fec_encoder = std::make_shared<FecEncoder>();

  if (fs::exists(video_path)) {
    interpreter.Init();
    module.Import();

    PyObject* initializer = module.GetAttr("reset_everything");
    if (PyCallable_Check(initializer)) {
      PyObject* init_args =
          Py_BuildValue("(ss)", video_path.c_str(), save_dir.c_str());
      PyObject* ret = PyObject_CallObject(initializer, init_args);
      Py_DECREF(initializer);
      Py_DECREF(init_args);
      if (!ret) {
        PyErr_Print();
        throw std::runtime_error("call reset_everything failed");
      }
      Py_DECREF(ret);
      encoder_func = module.GetAttr("wrapped_encode");
      decoder_func = module.GetAttr("wrapped_decode");
      on_decoder_feedback_func = module.GetAttr("on_decoder_feedback");
    } else {
      Py_DECREF(initializer);
      PyErr_Print();
      throw std::runtime_error("reset_everything is not callable");
    }
  }
  auto app0 =
      encoder_func
          ? std::make_unique<VideoSender>(
                encoder_func, on_decoder_feedback_func, fec_encoder, save_dir)
          : std::make_unique<VideoSender>(lookup_table, fec_encoder, save_dir);

  auto app1 = decoder_func
                  ? std::make_unique<VideoReceiver>(decoder_func, save_dir)
                  : std::make_unique<VideoReceiver>(lookup_table, save_dir);

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

  Py_XDECREF(encoder_func);
  Py_XDECREF(decoder_func);
  Py_XDECREF(on_decoder_feedback_func);
  return 0;
}
