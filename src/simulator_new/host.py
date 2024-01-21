from simulator_new.clock import ClockObserver
from simulator_new.pacer import Pacer
from simulator_new.packet import Packet


class Host(ClockObserver):
    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        self.id = id
        self.tx_link = tx_link
        self.rx_link = rx_link
        self.ts_ms = 0
        self.pacer = Pacer()
        self.pacer.set_pacing_rate_Bps(15000)
        self.cc = cc
        self.cc.register_host(self)
        self.rtx_mngr = rtx_mngr
        self.rtx_mngr.register_host(self)
        self.app = app
        self.app.register_host(self)
        self.recorder = None
        self.pkt_count = 0
        self.pkt_cls = Packet

    def _peek_pkt(self):
        # TODO: consider rtx
        return self.app.peek_pkt()

    def _get_pkt(self):
        """Get packet from appliaction layer or retransmission manager"""
        unacked_pkt = self.rtx_mngr.get_pkt()
        # prioritize retransmission
        if unacked_pkt is not None:
            return unacked_pkt
        pkt_size_byte, app_data = self.app.get_pkt()
        if pkt_size_byte > 0:
            pkt = self.pkt_cls(self.pkt_count, Packet.DATA_PKT, pkt_size_byte, app_data)
            return pkt
        return None

    def register_stats_recorder(self, recorder):
        self.recorder = recorder

    def can_send(self, pkt_size_byte):
        return self.pacer.can_send(pkt_size_byte)

    def _on_pkt_sent(self, ts_ms, pkt):
        # TODO: consider rtx pkts
        self.pkt_count += 1

    def _on_pkt_acked(self, ts_ms, data_pkt, ack_pkt):
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
                self.tx_link.push(pkt)
                self._on_pkt_sent(self.ts_ms, pkt)
                self.pacer.on_pkt_sent(pkt.size_bytes)
                self.cc.on_pkt_sent(self.ts_ms, pkt)
                self.rtx_mngr.on_pkt_sent(pkt)
                if self.recorder:
                    self.recorder.on_pkt_sent(self.ts_ms, pkt)
            else:
                break

    def receive(self) -> None:
        pkt = self.rx_link.pull()
        while pkt is not None:
            pkt.ts_rcvd_ms = self.ts_ms
            if pkt.is_data_pkt():
                self.app.deliver_pkt(pkt)
                if self.recorder:
                    self.recorder.on_pkt_received(self.ts_ms, pkt)
                # send ack pkt
                ack_pkt = Packet(pkt.pkt_id, Packet.ACK_PKT, 80, {})
                ack_pkt.ts_sent_ms = self.ts_ms
                if ack_pkt.ts_first_sent_ms == 0:
                    ack_pkt.ts_first_sent_ms = self.ts_ms
                ack_pkt.data_pkt_ts_sent_ms = pkt.ts_sent_ms
                ack_pkt.acked_size_bytes = pkt.size_bytes
                self.tx_link.push(ack_pkt)
            elif pkt.is_ack_pkt():
                data_pkt = self.rtx_mngr.unacked_buf[pkt.pkt_id]
                self._on_pkt_acked(self.ts_ms, data_pkt, pkt)
                self.cc.on_pkt_acked(self.ts_ms, data_pkt, pkt)
                self.rtx_mngr.on_pkt_acked(self.ts_ms, pkt)
                if self.recorder:
                    self.recorder.on_pkt_acked(self.ts_ms, pkt)
            pkt = self.rx_link.pull()

    def tick(self, ts_ms) -> None:
        assert self.ts_ms <= ts_ms
        self.ts_ms = ts_ms
        self.app.tick(ts_ms)
        self.pacer.tick(ts_ms)
        self.cc.tick(ts_ms)
        self.rtx_mngr.tick(ts_ms)
        self.send()
        self.receive()

    def reset(self) -> None:
        self.ts_ms = 0
        self.pacer.reset()
        self.pacer.set_pacing_rate_Bps(15000)
        self.cc.reset()
        self.rtx_mngr.reset()
        self.app.reset()
        if self.recorder:
            self.recorder.reset()
        self.pkt_count = 0
