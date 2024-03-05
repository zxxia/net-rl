from abc import abstractmethod

from simulator_new.clock import ClockObserver

class CongestionControl(ClockObserver):
    def __init__(self) -> None:
        self.host = None

    def register_host(self, host):
        self.host = host

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
