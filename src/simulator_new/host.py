from simulator_new.constant import BITS_PER_BYTE
from simulator_new.clock import ClockObserver
from simulator_new.packet import Packet


class Host(ClockObserver):
    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        self.id = id
        self.tx_link = tx_link
        self.rx_link = rx_link
        self.ts_ms = 0
        self.next_send_ts_ms = 0
        self.pacing_rate_byte_per_sec = 15000
        self.cc = cc
        self.cc.register_host(self)
        self.rtx_mngr = rtx_mngr
        self.rtx_mngr.register_host(self)
        self.app = app
        self.app.register_host(self)
        self.recorder = None
        self.pkt_count = 0

    def _has_app_data(self):
        return self.app.has_data()

    def _get_pkt(self):
        """Get packet from appliaction layer or retransmission manager"""
        unacked_pkt = self.rtx_mngr.get_pkt()
        # prioritize retransmission
        if unacked_pkt is not None:
            return unacked_pkt
        pkt_size_bytes, app_data = self.app.get_pkt()
        pkt = Packet(self.pkt_count, Packet.DATA_PKT, pkt_size_bytes, app_data)
        self.pkt_count += 1
        return pkt

    def register_stats_recorder(self, recorder):
        self.recorder = recorder

    def set_pacing_rate_mbps(self, rate_mbps):
        self.pacing_rate_byte_per_sec = rate_mbps * 1e6 / BITS_PER_BYTE

    def set_pacing_rate_byte_per_sec(self, rate_byte_per_sec):
        self.pacing_rate_byte_per_sec = rate_byte_per_sec

    def send(self) -> None:
        while self._has_app_data() and self.cc.can_send() and self.ts_ms >= self.next_send_ts_ms:
            pkt = self._get_pkt()
            pkt.ts_sent_ms = self.ts_ms
            if pkt.first_ts_sent_ms == 0:
                pkt.first_ts_sent_ms = self.ts_ms
            self.tx_link.push(pkt)
            self.cc.on_pkt_sent(self.ts_ms, pkt)
            self.rtx_mngr.on_pkt_sent(pkt)
            if self.recorder:
                self.recorder.on_pkt_sent(self.ts_ms, pkt)
            self.next_send_ts_ms += (pkt.size_bytes / self.pacing_rate_byte_per_sec) * 1000

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
                ack_pkt.data_pkt_ts_sent_ms = pkt.ts_sent_ms
                ack_pkt.acked_size_bytes = pkt.size_bytes
                self.tx_link.push(ack_pkt)
            elif pkt.is_ack_pkt():
                self.cc.on_pkt_acked(self.ts_ms, pkt)
                self.rtx_mngr.on_pkt_acked(self.ts_ms, pkt)
                if self.recorder:
                    self.recorder.on_pkt_acked(self.ts_ms, pkt)
            pkt = self.rx_link.pull()

    def tick(self, ts_ms) -> None:
        assert self.ts_ms <= ts_ms
        self.ts_ms = ts_ms
        self.app.tick(ts_ms)
        self.cc.tick(ts_ms)
        self.rtx_mngr.tick(ts_ms)
        self.send()
        self.receive()

    def reset(self) -> None:
        self.ts_ms = 0
        self.next_send_ts_ms = 0
        self.pacing_rate_byte_per_sec = 15000
        self.cc.reset()
        self.rtx_mngr.reset()
        self.app.reset()
        if self.recorder:
            self.recorder.reset()
        self.pkt_count = 0
