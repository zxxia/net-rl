import csv
import math
import os
from enum import Enum

from simulator_new.cc import CongestionControl
from simulator_new.cc.gcc.probe import ProbeController, estimate_probed_rate_Bps

GCC_START_RATE_BYTE_PER_SEC = 12500 * 3

class RemoteRateControllerState(Enum):
    INC = "Increase"
    DEC = "Decrease"
    HOLD = "Hold"


class BandwidthUsageSignal(Enum):
    OVERUSE = 'overuse'
    UNDERUSE = 'underuse'
    NORMAL = 'normal'


class ArrivalTimeFilter:
    K = 5
    def __init__(self) -> None:
        self.chi = 0.1
        self.q = 1e-3
        self.z = 0
        self.m_hat = 0
        self.var_v_hat = 0
        self.e = 0.1
        self.frame_first_pkt_sent_ts_list = []

    def add_frame_sent_time(self, t):
        if t is None:
            return
        self.frame_first_pkt_sent_ts_list.append(t)
        if len(self.frame_first_pkt_sent_ts_list) > self.K:
            self.frame_first_pkt_sent_ts_list = self.frame_first_pkt_sent_ts_list[1:]

    def update(self, delay_gradient):
        f_max = max([1 / ((t - t_prev) / 1000) for t_prev, t in
                     zip(self.frame_first_pkt_sent_ts_list[0:-1], self.frame_first_pkt_sent_ts_list[1:])])
        self.alpha = (1 - self.chi) ** (25 / (1000 * f_max))

        self.z = delay_gradient - self.m_hat
        self.var_v_hat = max(self.alpha * self.var_v_hat + (1 - self.alpha) * self.z**2, 1)
        z_new = min(self.z, 3 * math.sqrt(self.var_v_hat))
        self.k = (self.e + self.q) / (self.var_v_hat + (self.e + self.q))
        self.m_hat = self.m_hat + z_new * self.k
        self.e = (1-self.k) * (self.e + self.q)

        return self.m_hat


class RemoteRateController:
    ALPHA = 0.85
    ETA = 1.05

    def __init__(self) -> None:
        self.state = RemoteRateControllerState.INC
        self.est_rate_Bps = GCC_START_RATE_BYTE_PER_SEC  # A_r, 100Kbps
        self.update_ts_ms = 0

    def update_state(self, bw_use_signal):
        if self.state == RemoteRateControllerState.DEC:
            if bw_use_signal != BandwidthUsageSignal.OVERUSE:
                self.state = RemoteRateControllerState.HOLD
        elif self.state == RemoteRateControllerState.HOLD:
            if bw_use_signal == BandwidthUsageSignal.OVERUSE:
                self.state = RemoteRateControllerState.DEC
            elif bw_use_signal == BandwidthUsageSignal.NORMAL:
                self.state = RemoteRateControllerState.INC
        else: # INC
            if bw_use_signal == BandwidthUsageSignal.OVERUSE:
                self.state = RemoteRateControllerState.DEC
            elif bw_use_signal == BandwidthUsageSignal.UNDERUSE:
                self.state = RemoteRateControllerState.HOLD

    def update_rate_Bps(self, ts_ms, rcv_rate_Bps):
        if self.state == RemoteRateControllerState.INC:
            self.est_rate_Bps = min(self.ETA ** min((ts_ms - self.update_ts_ms) / 1000, 1) * self.est_rate_Bps, 1.5 * rcv_rate_Bps)
        elif self.state == RemoteRateControllerState.DEC:
            self.est_rate_Bps =  min(self.ALPHA * rcv_rate_Bps, 1.5 * rcv_rate_Bps)
        elif self.state == RemoteRateControllerState.HOLD:
            self.est_rate_Bps = min(self.est_rate_Bps, 1.5 * rcv_rate_Bps)
        else:
            raise RuntimeError("invalid RemoteRateControllerState.")
        self.update_ts_ms = ts_ms
        return self.est_rate_Bps

    def get_rate_Bps(self):
        return self.est_rate_Bps

    def set_rate_Bps(self, ts_ms, rate_Bps):
        self.est_rate_Bps = rate_Bps
        self.update_ts_ms = ts_ms


class OveruseDetector:
    def __init__(self) -> None:
        self.signal = BandwidthUsageSignal.NORMAL
        self.new_signal = BandwidthUsageSignal.NORMAL
        self.ts_overuse_start_ms = 0

    def generate_signal(self, ts_ms, estimated_delay_gradient, threshold):
        if estimated_delay_gradient > threshold:
            new_signal = BandwidthUsageSignal.OVERUSE
        elif estimated_delay_gradient < (-1) * threshold:
            new_signal = BandwidthUsageSignal.UNDERUSE
        else:
            new_signal = BandwidthUsageSignal.NORMAL

        if new_signal == BandwidthUsageSignal.OVERUSE:
            if new_signal != self.signal:
                if new_signal != self.new_signal:
                    self.new_signal = new_signal
                    self.ts_overuse_start_ms = ts_ms
                elif ts_ms - self.ts_overuse_start_ms >= 10:
                    self.signal = self.new_signal
        else:
            self.new_signal = new_signal
            self.signal = self.new_signal
        return self.signal


class DelayBasedController:

    def __init__(self):
        self.pkt_byte_rcvd = []
        self.pkt_ts_rcvd = []

        self.gamma = 5 # 12.5  # gradient threshold
        self.delay_gradient = 0
        self.delay_gradient_hat = 0

        self.remote_rate_controller = RemoteRateController()
        self.overuse_detector = OveruseDetector()
        self.arrival_time_filter = ArrivalTimeFilter()
        self.host = None
        self.rcv_rate_Bps = 0

    def register_host(self, host):
        self.host = host

    def reset(self):
        self.pkt_byte_rcvd = []
        self.pkt_ts_rcvd = []

        self.gamma = 5 # 12.5
        self.delay_gradient = 0
        self.delay_gradient_hat = 0

        self.remote_rate_controller = RemoteRateController()
        self.overuse_detector = OveruseDetector()
        self.arrival_time_filter = ArrivalTimeFilter()
        self.rcv_rate_Bps = 0

    def on_pkt_rcvd(self, ts_ms, pkt):
        self.pkt_byte_rcvd.append(pkt.size_bytes)
        self.pkt_ts_rcvd.append(ts_ms)

    def on_frame_rcvd(self, ts_ms, frame_last_pkt_sent_ts_ms,
                      frame_last_pkt_rcv_ts_ms,
                      prev_frame_last_pkt_sent_ts_ms,
                      prev_frame_last_pkt_rcv_ts_ms):
        i = 0
        while i < len(self.pkt_ts_rcvd):
            if ts_ms - self.pkt_ts_rcvd[i] > 500:
                i += 1
            else:
                break
        self.pkt_ts_rcvd = self.pkt_ts_rcvd[i:]
        self.pkt_byte_rcvd = self.pkt_byte_rcvd[i:]

        wnd_len_sec = ts_ms / 1000 if ts_ms < 500 else 0.5
        self.rcv_rate_Bps = sum(self.pkt_byte_rcvd) / wnd_len_sec

        self.arrival_time_filter.add_frame_sent_time(frame_last_pkt_sent_ts_ms)
        if frame_last_pkt_rcv_ts_ms is None or \
           frame_last_pkt_sent_ts_ms is None or \
           prev_frame_last_pkt_sent_ts_ms is None or \
           prev_frame_last_pkt_rcv_ts_ms is None:
            return

        self.delay_gradient = (frame_last_pkt_rcv_ts_ms - prev_frame_last_pkt_rcv_ts_ms) - \
                (frame_last_pkt_sent_ts_ms - prev_frame_last_pkt_sent_ts_ms)

        self.delay_gradient_hat = self.arrival_time_filter.update(self.delay_gradient)

        # adaptively adjust threshold
        ku, kd = 0.01, 0.00018
        k_gamma = kd if abs(self.delay_gradient_hat) < self.gamma else ku
        if abs(self.delay_gradient_hat) - self.gamma <= 15:
            self.gamma = self.gamma + (frame_last_pkt_rcv_ts_ms -
                                       prev_frame_last_pkt_rcv_ts_ms) * \
                    k_gamma * (abs(self.delay_gradient_hat) - self.gamma)

        overuse_signal = self.overuse_detector.generate_signal(
            ts_ms, self.delay_gradient_hat, self.gamma)

        self.remote_rate_controller.update_state(overuse_signal)

        old_estimated_rate_Bps = self.remote_rate_controller.get_rate_Bps()
        new_estimated_rate_Bps = self.remote_rate_controller.update_rate_Bps(
            ts_ms,  self.rcv_rate_Bps)
        if new_estimated_rate_Bps > 0:
            # send REMB message
            if self.host and new_estimated_rate_Bps < 0.97 * old_estimated_rate_Bps:
                self.host.send_rtcp_report(ts_ms, new_estimated_rate_Bps)

class LossBasedController:

    def __init__(self) -> None:
        self.estimated_rate_Bps = GCC_START_RATE_BYTE_PER_SEC  # 100Kbps

    def on_rtcp_report(self, loss_fraction):
        if loss_fraction > 0.1:
            self.estimated_rate_Bps *= 1 - 0.5 * loss_fraction
        elif loss_fraction < 0.02:
            self.estimated_rate_Bps *= 1.05
        else:
            pass
        return self.estimated_rate_Bps

    def reset(self):
        self.estimated_rate_Bps = GCC_START_RATE_BYTE_PER_SEC  # 100Kbps


class GCC(CongestionControl):

    def __init__(self, save_dir=None) -> None:
        super().__init__()
        self.loss_based_controller = LossBasedController()
        self.delay_based_controller = DelayBasedController()
        self.save_dir = save_dir
        self.gcc_log_path = None
        self.gcc_log = None
        self.csv_writer = None
        self.est_rate_Bps = GCC_START_RATE_BYTE_PER_SEC
        self.probe_ctlr = ProbeController(self.est_rate_Bps)
        if self.probe_ctlr.is_enabled():
            self.est_rate_Bps = self.probe_ctlr.get_probe_rate_Bps()

    def __del__(self):
        if self.gcc_log:
            self.gcc_log.close()

    def get_est_rate_Bps(self, start_ts_ms, end_ts_ms):
        return self.est_rate_Bps

    def on_pkt_to_send(self, pkt):
        if self.probe_ctlr.is_enabled():
            self.probe_ctlr.mark_pkt(pkt)

    def on_pkt_sent(self, ts_ms, pkt):
        if pkt.is_rtp_pkt():
            if self.probe_ctlr.is_enabled():
                self.probe_ctlr.on_pkt_sent(ts_ms)
        elif pkt.is_rtcp_pkt() and pkt.probe_info:
            probed_rate = estimate_probed_rate_Bps(pkt.probe_info)
            self.delay_based_controller.remote_rate_controller.set_rate_Bps(
                ts_ms, probed_rate)

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def register_host(self, host):
        super().register_host(host)
        self.delay_based_controller.register_host(host)
        assert self.host

        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            self.gcc_log_path = os.path.join(self.save_dir, 'gcc_log_{}.csv'.format(self.host.id))
            self.gcc_log = open(self.gcc_log_path, 'w', 1)
            self.csv_writer = csv.writer(self.gcc_log, lineterminator='\n')
            self.csv_writer.writerow(
                ['timestamp_ms', "pacing_rate_Bps", "est_rate_Bps",
                 "delay_based_est_rate_Bps",
                 "loss_based_est_rate_Bps", "remote_rate_controller_state",
                 "delay_gradient", "delay_gradient_hat", "gamma",
                 'loss_fraction', 'rcv_rate_Bps', "overuse_signal"])

    def on_pkt_rcvd(self, ts_ms, pkt):
        if pkt.is_rtp_pkt():
            self.delay_based_controller.on_pkt_rcvd(pkt.ts_rcvd_ms, pkt)
        elif pkt.is_rtcp_pkt():
            if pkt.probe_info:
                self.loss_based_controller.estimated_rate_Bps = estimate_probed_rate_Bps(pkt.probe_info)
            self.loss_based_controller.on_rtcp_report(pkt.loss_fraction)
            if pkt.probe_info:
                self.est_rate_Bps = min(estimate_probed_rate_Bps(pkt.probe_info),
                    self.loss_based_controller.estimated_rate_Bps)
            else:
                self.est_rate_Bps = min(pkt.estimated_rate_Bps,
                    self.loss_based_controller.estimated_rate_Bps)
            self.loss_based_controller.estimated_rate_Bps = self.est_rate_Bps
            assert self.host
            if self.csv_writer:
                self.csv_writer.writerow(
                    [ts_ms, self.host.pacer.pacing_rate_Bps, self.est_rate_Bps,
                     pkt.estimated_rate_Bps,
                     self.loss_based_controller.estimated_rate_Bps,
                     self.delay_based_controller.remote_rate_controller.state.value,
                     self.delay_based_controller.delay_gradient,
                     self.delay_based_controller.delay_gradient_hat,
                     self.delay_based_controller.gamma,
                     pkt.loss_fraction])
        elif pkt.is_nack_pkt():
            pass
        else:
            raise NotImplementedError("Unknown " + pkt.pkt_type)

    def on_frame_rcvd(self, ts_ms, frame_last_pkt_sent_ts_ms,
                      frame_last_pkt_rcv_ts_ms, prev_frame_last_pkt_sent_ts_ms,
                      prev_frame_last_pkt_rcv_ts_ms):

        self.delay_based_controller.on_frame_rcvd(
            ts_ms, frame_last_pkt_sent_ts_ms, frame_last_pkt_rcv_ts_ms,
            prev_frame_last_pkt_sent_ts_ms, prev_frame_last_pkt_rcv_ts_ms)
        assert self.host
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, self.host.pacer.pacing_rate_Bps, self.est_rate_Bps,
                 self.delay_based_controller.remote_rate_controller.get_rate_Bps(),
                 0,
                 self.delay_based_controller.remote_rate_controller.state.value,
                 self.delay_based_controller.delay_gradient,
                 self.delay_based_controller.delay_gradient_hat,
                 self.delay_based_controller.gamma, 0,
                 self.delay_based_controller.rcv_rate_Bps,
                 self.delay_based_controller.overuse_detector.signal.value])

    def tick(self, ts_ms):
        assert self.host
        self.probe_ctlr.tick(ts_ms)
        if self.probe_ctlr.is_enabled():
            self.est_rate_Bps = self.probe_ctlr.get_probe_rate_Bps()

    def reset(self):
        self.delay_based_controller.reset()
        self.loss_based_controller.reset()
        self.est_rate_Bps = GCC_START_RATE_BYTE_PER_SEC
        self.probe_ctlr = ProbeController(self.est_rate_Bps)
        if self.probe_ctlr.is_enabled():
            self.est_rate_Bps = self.probe_ctlr.get_probe_rate_Bps()
