from enum import Enum

from simulator_new.cc import CongestionControl

class RemoteRateControllerState(Enum):
    INC = "Increase"
    DEC = "Decrease"
    HOLD = "Hold"


class BandwidthUsageSignal(Enum):
    OVERUSE = 'overuse'
    UNDERUSE = 'underuse'
    NORMAL = 'normal'


class RemoteRateController:
    ALPHA = 0.85
    ETA = 1.05

    def __init__(self) -> None:
        self.state = RemoteRateControllerState.INC

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

    def get_rate_Bps(self, old_estimated_rate_Bps, rcv_rate_Bps):
        if self.state == RemoteRateControllerState.INC:
            return min(self.ETA * old_estimated_rate_Bps, 1.5 * rcv_rate_Bps)
        elif self.state == RemoteRateControllerState.DEC:
            return min(self.ALPHA * rcv_rate_Bps, 1.5 * rcv_rate_Bps)
        elif self.state == RemoteRateControllerState.HOLD:
            return min(old_estimated_rate_Bps, 1.5 * rcv_rate_Bps)
        else:
            raise RuntimeError("invalid RemoteRateControllerState.")


class OveruseDetector:
    def __init__(self) -> None:
        self.signal = BandwidthUsageSignal.NORMAL
        self.new_signal = BandwidthUsageSignal.NORMAL
        self.ts_condition_start_ms = 0

    def generate_signal(self, ts_ms, estimated_delay_gradient, threshold):
        if estimated_delay_gradient > threshold:
            new_signal = BandwidthUsageSignal.OVERUSE
        elif estimated_delay_gradient < (-1) * threshold:
            new_signal = BandwidthUsageSignal.UNDERUSE
        else:
            new_signal = BandwidthUsageSignal.NORMAL

        if new_signal != self.new_signal:
            self.new_signal = new_signal
            self.ts_condition_start_ms = ts_ms
        elif new_signal == self.new_signal and ts_ms - self.ts_condition_start_ms > 100:
            self.signal = self.new_signal
        else:
            pass
        return self.signal


class DelayBasedController:

    def __init__(self):
        self.pkt_byte_rcvd = []
        self.pkt_ts_rcvd = []

        self.estimated_rate_Bps = 12500  # A_r, 100Kbps

        self.gamma = 1  # gradient threshold

        self.remote_rate_controller = RemoteRateController()
        self.overuse_detector = OveruseDetector()
        self.host = None

    def register_host(self, host):
        self.host = host

    def reset(self):
        self.pkt_byte_rcvd = []
        self.pkt_ts_rcvd = []
        self.estimated_rate_Bps = 12500  # A_r, 100Kbps

        self.gamma = 1

        self.remote_rate_controller = RemoteRateController()
        self.overuse_detector = OveruseDetector()

    def on_pkt_rcvd(self, ts_ms, pkt):
        self.pkt_byte_rcvd.append(pkt.size_bytes)
        self.pkt_ts_rcvd.append(ts_ms)

    def on_frame_rcvd(self, ts_ms, frame_first_pkt_rcv_ts_ms,
                      frame_last_pkt_rcv_ts_ms,
                      prev_frame_first_pkt_rcv_ts_ms,
                      prev_frame_last_pkt_rcv_ts_ms):
        for pkt_ts_ms in self.pkt_ts_rcvd:
            if ts_ms - pkt_ts_ms > 500:
                self.pkt_ts_rcvd.pop(0)
                self.pkt_byte_rcvd.pop(0)
            else:
                break
        wnd_len_sec = ts_ms / 1000 if ts_ms < 500 else 0.5
        rcv_rate_Bps = sum(self.pkt_byte_rcvd) / wnd_len_sec

        if prev_frame_last_pkt_rcv_ts_ms is None or prev_frame_last_pkt_rcv_ts_ms is None:
            return

        delay_gradient = (frame_last_pkt_rcv_ts_ms - prev_frame_last_pkt_rcv_ts_ms) - \
                (frame_first_pkt_rcv_ts_ms - prev_frame_first_pkt_rcv_ts_ms)

        # TODO: filter delay_gradient with Kalman filter

        # adaptively adjust threshold
        ku, kd = 0.01, 0.00018
        k_gamma = kd if abs(delay_gradient) < self.gamma else ku
        self.gamma = self.gamma + (frame_last_pkt_rcv_ts_ms -
                                   prev_frame_last_pkt_rcv_ts_ms) * \
                k_gamma * (abs(delay_gradient) - self.gamma)

        overuse_signal = self.overuse_detector.generate_signal(
            ts_ms, delay_gradient, self.gamma)

        self.remote_rate_controller.update_state(overuse_signal)

        new_estimated_rate_Bps = self.remote_rate_controller.get_rate_Bps(
            self.estimated_rate_Bps, rcv_rate_Bps)
        if new_estimated_rate_Bps > 0:
            # send REMB message
            if self.host and new_estimated_rate_Bps < 0.97 * self.estimated_rate_Bps:
                self.host.send_rtcp_report(ts_ms, new_estimated_rate_Bps)
            self.estimated_rate_Bps = new_estimated_rate_Bps

class LossBasedController:

    def __init__(self) -> None:
        self.estimated_rate_Bps = 12500  # 100Kbps

    def on_rtcp_report(self, loss_fraction):
        if loss_fraction > 0.1:
            self.estimated_rate_Bps *= 1 - 0.5 * loss_fraction
        elif loss_fraction < 0.02:
            self.estimated_rate_Bps *= 1.05
        else:
            pass
        return self.estimated_rate_Bps

    def reset(self):
        self.estimated_rate_Bps = 12500  # 100Kbps


class GCC(CongestionControl):

    def __init__(self) -> None:
        super().__init__()
        self.loss_based_controller = LossBasedController()
        self.delay_based_controller = DelayBasedController()

    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_acked(self, ts_ms, data_pkt, ack_pkt):
        pass

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def register_host(self, host):
        super().register_host(host)
        self.delay_based_controller.register_host(host)
        assert self.host
        self.host.pacer.set_pacing_rate_Bps(
            self.delay_based_controller.estimated_rate_Bps)

    def on_pkt_rcvd(self, pkt):
        if pkt.is_rtp_pkt():
            self.delay_based_controller.on_pkt_rcvd(pkt.ts_rcvd_ms, pkt)
        elif pkt.is_rtcp_pkt():
            self.loss_based_controller.on_rtcp_report(pkt.loss_fraction)
            assert self.host
            estimated_rate_Bps = min(pkt.estimated_rate_Bps,
                self.loss_based_controller.estimated_rate_Bps)
            self.host.pacer.set_pacing_rate_Bps(estimated_rate_Bps)
        else:
            raise NotImplementedError("Unknown " + pkt.pkt_type)

    def on_frame_rcvd(self, ts_ms, frame_first_pkt_rcv_ts_ms,
                      frame_last_pkt_rcv_ts_ms, prev_frame_first_pkt_rcv_ts_ms,
                      prev_frame_last_pkt_rcv_ts_ms):

        self.delay_based_controller.on_frame_rcvd(
            ts_ms, frame_first_pkt_rcv_ts_ms, frame_last_pkt_rcv_ts_ms,
            prev_frame_first_pkt_rcv_ts_ms, prev_frame_last_pkt_rcv_ts_ms)

    def tick(self, ts_ms):
        pass

    def reset(self):
        self.delay_based_controller.reset()
        self.loss_based_controller.reset()
