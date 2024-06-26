from simulator_new.clock import ClockObserver

class RtxManager(ClockObserver):

    def __init__(self) -> None:
        self.host = None

    def register_host(self, host):
        self.host = host

    def on_pkt_sent(self, pkt):
        # TODO: add unacked pkt to an unack buffer
        pass

    def on_pkt_rcvd(self, ts_ms, pkt):
        # TODO: remove acked pkt from the unack buffer
        # TODO: mark pkt as lost if out of order happens and move the pkt from
        # unack buffer to rtx buffer
        pass

    def peek_pkt(self):
        return 0

    def get_pkt(self):
        return None

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass

    def get_buffered_pkt(self, pkt_id):
        return None
