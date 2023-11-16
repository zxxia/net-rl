from simulator_new.clock import ClockObserver

class CongestionControl(ClockObserver):
    def __init__(self) -> None:
        self.host = None
        pass

    def register_host(self, host):
        self.host = host

    def can_send(self):
        return True

    def on_pkt_sent(self, pkt):
        pass

    def on_pkt_acked(self, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass
