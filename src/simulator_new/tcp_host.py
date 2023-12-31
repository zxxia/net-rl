from simulator_new.cc import BBRv1
from simulator_new.constant import TCP_INIT_CWND_BYTE
from simulator_new.host import Host
from simulator_new.packet import BBRPacket


class TCPHost(Host):
    """Simulate TCP behavior
    srtt reference: https://datatracker.ietf.org/doc/html/rfc6298
    """

    SRTT_ALPHA = 1 / 8
    SRTT_BETA = 1 / 4
    RTO_K = 4

    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        self.bytes_in_flight = 0
        self.srtt_ms = 0
        self.rttvar_ms = 0
        assert isinstance(cc, BBRv1)
        self.cwnd_byte = TCP_INIT_CWND_BYTE
        super().__init__(id, tx_link, rx_link, cc, rtx_mngr, app)
        self.pkt_cls = BBRPacket

    def can_send(self):
        return self._has_app_data() and self.bytes_in_flight < self.cwnd_byte and self.ts_ms >= self.next_send_ts_ms

    def on_pkt_sent(self, pkt):
        self.bytes_in_flight += pkt.size_bytes

    def on_pkt_acked(self, pkt):
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

    def reset(self) -> None:
        self.bytes_in_flight = 0
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.cwnd_byte = TCP_INIT_CWND_BYTE
        super().reset()
