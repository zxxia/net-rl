from simulator_new.app import FileSender, FileReceiver, Encoder, Decoder
from simulator_new.cc import Aurora, BBRv1, NoCC, GCC, OracleCC, OracleNoPredictCC
from simulator_new.constant import MSS
from simulator_new.host import Host
from simulator_new.aurora_host import AuroraHost
from simulator_new.tcp_host import TCPHost
from simulator_new.rtp_host import RTPHost
from simulator_new.link import Link
from simulator_new.rtx_manager import AuroraRtxManager, WebRtcRtxManager, TCPRtxManager
from simulator_new.stats_recorder import StatsRecorder
from simulator_new.plot.plot import plot_gcc_log, plot_mi_log, plot_pkt_log

class Simulator:
    def __init__(self, trace, save_dir, cc="", app="file_transfer", **kwargs) -> None:
        self.trace = trace
        self.save_dir = save_dir
        self.data_link = Link('datalink', trace, prop_delay_ms=trace.min_delay,
                              queue_cap_bytes=trace.queue_size * MSS,
                              pkt_loss_rate=trace.loss_rate)
        self.ack_link = Link('acklink', None, prop_delay_ms=trace.min_delay)

        self.recorder = StatsRecorder(self.save_dir, self.data_link, self.ack_link)

        if cc == 'aurora':
            self.aurora_model_path = kwargs.get("model_path", "")
            ae_guided = kwargs.get("ae_guided", False)
            self.sender_cc = Aurora(self.aurora_model_path, save_dir=self.save_dir,
                                    ae_guided=ae_guided)
            self.sender_rtx_mngr = AuroraRtxManager()
            sender_host = AuroraHost

            self.receiver_cc = NoCC()
            self.receiver_rtx_mngr = None
            receiver_host = AuroraHost
        elif cc == 'bbr':
            self.sender_cc = BBRv1(seed=42)
            self.sender_rtx_mngr = TCPRtxManager()
            sender_host = TCPHost
            self.receiver_cc = NoCC()
            self.receiver_rtx_mngr = None
            receiver_host = TCPHost
        elif cc == 'cubic':
            sender_host = TCPHost
            receiver_host = TCPHost
            self.receiver_cc = NoCC()
            self.receiver_rtx_mngr = None
            raise NotImplementedError
        elif cc == 'gcc':
            sender_host = RTPHost
            self.sender_cc = GCC(save_dir)
            self.sender_rtx_mngr = WebRtcRtxManager()

            self.receiver_cc = GCC(save_dir)
            self.receiver_rtx_mngr = None
            receiver_host = RTPHost
        elif cc == 'oracle':
            self.sender_cc = OracleCC(trace)
            self.sender_rtx_mngr = AuroraRtxManager()
            sender_host = AuroraHost

            self.receiver_cc = NoCC()
            self.receiver_rtx_mngr = None
            receiver_host = AuroraHost
        elif cc == 'oracle_no_predict':
            self.sender_cc = OracleNoPredictCC(trace)
            self.sender_rtx_mngr = AuroraRtxManager()
            sender_host = AuroraHost

            self.receiver_cc = NoCC()
            self.receiver_rtx_mngr = None
            receiver_host = AuroraHost
        else:
            self.sender_cc = NoCC()
            self.sender_rtx_mngr = None
            sender_host = Host
        if app == 'file_transfer':
            self.sender_app = FileSender()
            self.receiver_app = FileReceiver()
        elif app == 'video_streaming':
            lookup_table_path = kwargs['lookup_table_path']
            self.sender_app = Encoder(lookup_table_path)
            self.receiver_app = Decoder(lookup_table_path, save_dir=self.save_dir)
        else:
            raise NotImplementedError

        self.sender = sender_host(0, self.data_link, self.ack_link,
                                  self.sender_cc, self.sender_rtx_mngr,
                                  self.sender_app, save_dir=self.save_dir)
        self.sender.register_stats_recorder(self.recorder)

        self.receiver = receiver_host(1, self.ack_link, self.data_link,
                                      self.receiver_cc, self.receiver_rtx_mngr,
                                      self.receiver_app)
        self.receiver.register_stats_recorder(self.recorder)

        self.sender.register_other_host(self.receiver)
        self.receiver.register_other_host(self.sender)

    def simulate(self, dur_sec, summary=True):
        dur_ms = dur_sec * 1000
        for ts_ms in range(dur_ms):
            self.tick(ts_ms)
        if summary:
            self.summary()

    def summary(self):
        sender_cc_name = self.sender_cc.__class__.__name__.lower()
        self.recorder.summary()
        print(f'trace avg bw={self.trace.avg_bw:.2f}Mbps')
        if isinstance(self.sender_cc, Aurora) and self.sender_cc.mi_log_path:
            plot_mi_log(self.data_link.bw_trace, self.sender_cc.mi_log_path,
                        self.save_dir, sender_cc_name)
        if isinstance(self.sender_cc, GCC) and isinstance(self.receiver_cc, GCC) \
            and self.sender_cc.gcc_log_path and self.receiver_cc.gcc_log_path:
            plot_gcc_log(self.data_link.bw_trace, self.sender_cc.gcc_log_path,
                         self.receiver_cc.gcc_log_path, self.sender.pacer.log_path, self.save_dir)
        if self.recorder.log_fname:
            rcvr_app_log_name = self.receiver_app.log_fname \
                if isinstance(self.receiver_app, Decoder) else None
            plot_pkt_log(self.data_link.bw_trace, self.recorder.log_fname,
                         self.save_dir, sender_cc_name, rcvr_app_log_name)

    def tick(self, ts_ms):
        self.data_link.tick(ts_ms)
        self.ack_link.tick(ts_ms)
        self.sender.tick(ts_ms)
        self.receiver.tick(ts_ms)

    def reset(self):
        self.data_link.reset()
        self.ack_link.reset()
        self.sender.reset()
        self.receiver.reset()
