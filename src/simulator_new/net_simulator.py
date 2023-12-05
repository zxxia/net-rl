from simulator_new.app import FileSender, FileReceiver, Encoder, Decoder
from simulator_new.cc import CongestionControl, Aurora, BBRv1
from simulator_new.constant import MSS
from simulator_new.host import Host
from simulator_new.link import Link
from simulator_new.rtx_manager import AuroraRtxManager, RtxManager, TCPRtxManager
from simulator_new.stats_recorder import StatsRecorder
from simulator_new.plot.plot import plot_decoder_log, plot_mi_log, plot_pkt_log

class Simulator:
    def __init__(self, trace, save_dir, cc="", app="file_transfer", **kwargs) -> None:
        self.trace = trace
        self.save_dir = save_dir
        self.data_link = Link('datalink', trace,
                              queue_cap_bytes=trace.queue_size * MSS,
                              pkt_loss_rate=trace.loss_rate)
        self.ack_link = Link('acklink', None)

        self.recorder = StatsRecorder(self.save_dir)

        self.aurora_model_path = kwargs.get("model_path", "")
        if cc == 'aurora':
            self.sender_cc = Aurora(self.aurora_model_path, save_dir=self.save_dir)
            self.sender_rtx_mngr = AuroraRtxManager()
        elif cc == 'bbr':
            self.sender_cc = BBRv1(seed=42)
            self.sender_rtx_mngr = TCPRtxManager()
        elif cc == 'cubic':
            raise NotImplementedError
        else:
            self.sender_cc = CongestionControl()
            self.sender_rtx_mngr = AuroraRtxManager()

        if app == 'file_transfer':
            self.sender_app = FileSender()
            self.receiver_app = FileReceiver()
        elif app == 'video_streaming':
            lookup_table_path = kwargs['lookup_table_path']
            self.sender_app = Encoder(lookup_table_path)
            self.receiver_app = Decoder(lookup_table_path, save_dir=self.save_dir)
        else:
            raise NotImplementedError

        self.sender = Host(0, self.data_link, self.ack_link, self.sender_cc,
                           self.sender_rtx_mngr, self.sender_app)
        self.sender.register_stats_recorder(self.recorder)

        self.receiver_cc = CongestionControl()
        self.receiver_rtx_mngr = RtxManager()
        self.receiver = Host(1, self.ack_link, self.data_link,
                             self.receiver_cc, self.receiver_rtx_mngr,
                             self.receiver_app)
        self.receiver.register_stats_recorder(self.recorder)

    def simulate(self, dur_sec):
        dur_ms = dur_sec * 1000
        for ts_ms in range(dur_ms):
            self.tick(ts_ms)
        self.summerize()

    def summerize(self):
        sender_cc_name = self.sender_cc.__class__.__name__.lower()
        self.recorder.summary()
        print(f'trace avg bw={self.trace.avg_bw:.2f}Mbps')
        if isinstance(self.sender_cc, Aurora) and self.sender_cc.mi_log_path:
            plot_mi_log(self.data_link.bw_trace, self.sender_cc.mi_log_path,
                        self.save_dir, sender_cc_name)
        if self.recorder.log_fname:
            plot_pkt_log(self.data_link.bw_trace, self.recorder.log_fname,
                        self.save_dir, sender_cc_name)
        if isinstance(self.receiver_app, Decoder) and self.receiver_app.log_fname:
            plot_decoder_log(self.receiver_app.log_fname, self.save_dir, sender_cc_name)

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
