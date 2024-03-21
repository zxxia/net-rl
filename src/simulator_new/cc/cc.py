from abc import abstractmethod

from simulator_new.clock import ClockObserver

class CongestionControl(ClockObserver):
    def __init__(self) -> None:
        self.host = None

    def register_host(self, host):
        self.host = host

    def on_pkt_to_send(self, pkt):
        pass

    @abstractmethod
    def on_pkt_sent(self, ts_ms, pkt):
        pass

    @abstractmethod
    def on_pkt_rcvd(self, ts_ms, pkt):
        pass

    @abstractmethod
    def on_pkt_lost(self, ts_ms, pkt):
        pass


class NoCC(CongestionControl):
    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_rcvd(self, ts_ms, pkt):
        pass

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass

    def get_est_rate_Bps(self, start_ts_ms, end_ts_ms):
        return 0

class OracleCC(CongestionControl):
    def __init__(self, trace) -> None:
        super().__init__()
        self.trace = trace

    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_rcvd(self, ts_ms, pkt):
        pass

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass

    def get_est_rate_Bps(self, start_ts_ms, end_ts_ms):
        return self.trace.get_avail_bits2send(
            start_ts_ms / 1000, end_ts_ms / 1000) * 1000 / 8 / \
            (end_ts_ms - start_ts_ms)


class OracleNoPredictCC(CongestionControl):
    def __init__(self, trace) -> None:
        super().__init__()
        self.trace = trace

    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_rcvd(self, ts_ms, pkt):
        pass

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass

    def get_est_rate_Bps(self, start_ts_ms, end_ts_ms):
        return self.trace.get_bandwidth(start_ts_ms / 1000) * 1e6 / 8
