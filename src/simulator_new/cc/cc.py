from abc import abstractmethod

from simulator_new.clock import ClockObserver
from simulator_new.constant import TCP_INIT_CWND_BYTE

class CongestionControl(ClockObserver):
    def __init__(self) -> None:
        self.host = None

    def register_host(self, host):
        self.host = host

    @abstractmethod
    def can_send(self):
        pass

    @abstractmethod
    def on_pkt_sent(self, ts_ms, pkt):
        pass

    @abstractmethod
    def on_pkt_acked(self, ts_ms, pkt):
        pass

    @abstractmethod
    def on_pkt_lost(self, ts_ms, pkt):
        pass


class NoCC(CongestionControl):
    def can_send(self):
        return True

    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_acked(self, ts_ms, pkt):
        pass

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        pass


class TCPCongestionControl(CongestionControl):
    """

    srtt reference: https://datatracker.ietf.org/doc/html/rfc6298
    """

    SRTT_ALPHA = 1 / 8
    SRTT_BETA = 1 / 4
    RTO_K = 4

    def __init__(self) -> None:
        super().__init__()
        self.bytes_in_flight = 0
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.cwnd_byte = TCP_INIT_CWND_BYTE

    def on_pkt_sent(self, ts_ms, pkt):
        self.bytes_in_flight += pkt.size_bytes

    def on_pkt_acked(self, ts_ms, pkt):
        self.bytes_in_flight -= pkt.acked_size_bytes
        if self.srtt_ms == 0 and self.rttvar_ms == 0:
            self.srtt_ms = pkt.rtt_ms()
            self.rttvar_ms = pkt.rtt_ms() / 2
        elif self.srtt_ms and self.rttvar_ms:
            self.srtt_ms = (1 - self.SRTT_ALPHA) * self.srtt_ms + \
                self.SRTT_ALPHA * pkt.rtt_ms()
            self.rttvar_ms = (1 - self.SRTT_BETA) * self.rttvar_ms + \
                self.SRTT_BETA * abs(self.srtt_ms - pkt.rtt_ms())
        else:
            raise ValueError("srtt and rttvar should be both 0 or both non-zeros.")
        rto_ms = max(1000, min(self.srtt_ms + self.RTO_K * self.rttvar_ms, 60000))
        # TODO: update rtx timer timeout value here

    def reset(self):
        super().reset()
        self.bytes_in_flight = 0
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.cwnd_byte = TCP_INIT_CWND_BYTE
