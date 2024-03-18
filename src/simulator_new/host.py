from simulator_new.clock import ClockObserver
from simulator_new.pacer import Pacer
from simulator_new.packet import Packet


class Host(ClockObserver):
    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        self.id = id
        self.tx_link = tx_link
        self.tx_link.register_host(self)
        self.rx_link = rx_link
        self.ts_ms = 0
        self.pacer = Pacer()
        self.pacer.set_pacing_rate_Bps(15000)
        self.cc = cc
        self.cc.register_host(self)
        self.rtx_mngr = rtx_mngr
        if self.rtx_mngr:
            self.rtx_mngr.register_host(self)
        self.app = app
        self.app.register_host(self)
        self.recorder = None
        self.pkt_id = 0
        self.pkt_cls = Packet

    def _peek_pkt(self):
        unacked_pkt_size = self.rtx_mngr.peek_pkt() if self.rtx_mngr else 0
        return self.app.peek_pkt() if unacked_pkt_size == 0 else unacked_pkt_size

    def _get_pkt(self):
        """Get packet from appliaction layer or retransmission manager"""
        pkt = self.rtx_mngr.get_pkt() if self.rtx_mngr else None
        # prioritize retransmission
        if pkt is not None:
            # print(self.ts_ms, "rtx", pkt.pkt_id, pkt.app_data)
            return pkt
        pkt_size_byte, app_data = self.app.get_pkt()
        if pkt_size_byte > 0:
            pkt = self.pkt_cls(self.pkt_id, self.pkt_cls.DATA_PKT, pkt_size_byte, app_data)
            return pkt
        return None

    def register_stats_recorder(self, recorder):
        self.recorder = recorder

    def can_send(self, pkt_size_byte):
        return self.pacer.can_send(pkt_size_byte)

    def _on_pkt_sent(self, pkt):
        # do not count
        if pkt.ts_sent_ms == pkt.ts_first_sent_ms:
            self.pkt_id += 1

    def _on_pkt_rcvd(self, pkt):
        pass

    def send(self) -> None:
        while True:
            pkt_size_byte = self._peek_pkt()
            if pkt_size_byte > 0 and self.can_send(pkt_size_byte):
                pkt = self._get_pkt()
                assert pkt is not None
                pkt.ts_sent_ms = self.ts_ms
                if pkt.ts_first_sent_ms == 0:
                    pkt.ts_first_sent_ms = self.ts_ms
                self.cc.on_pkt_to_send(pkt)
                self.tx_link.push(pkt)
                self._on_pkt_sent(pkt)
                self.pacer.on_pkt_sent(pkt.size_bytes)
                self.cc.on_pkt_sent(self.ts_ms, pkt)
                if self.rtx_mngr:
                    self.rtx_mngr.on_pkt_sent(pkt)
                if self.recorder:
                    self.recorder.on_pkt_sent(self.ts_ms, pkt)
            else:
                break

    def receive(self) -> None:
        pkt = self.rx_link.pull()
        while pkt is not None:
            pkt.ts_rcvd_ms = self.ts_ms
            self._on_pkt_rcvd(pkt)
            pkt = self.rx_link.pull()

    def tick(self, ts_ms) -> None:
        assert self.ts_ms <= ts_ms
        self.ts_ms = ts_ms
        self.app.tick(ts_ms)
        self.pacer.tick(ts_ms)
        self.cc.tick(ts_ms)
        if self.rtx_mngr:
            self.rtx_mngr.tick(ts_ms)
        self.send()
        self.receive()

    def reset(self) -> None:
        self.ts_ms = 0
        self.pacer.reset()
        self.pacer.set_pacing_rate_Bps(15000)
        self.cc.reset()
        if self.rtx_mngr:
            self.rtx_mngr.reset()
        self.app.reset()
        if self.recorder:
            self.recorder.reset()
        self.pkt_id = 0
