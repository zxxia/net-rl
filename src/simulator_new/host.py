from simulator_new.clock import ClockObserver
from simulator_new.constant import MSS
from simulator_new.packet import Packet

class CongestionControl:
    def __init__(self) -> None:
        pass

    def can_send(self):
        return True

    def on_packet_sent(self, pkt):
        pass

    def on_packet_acked(self, pkt):
        pass

class Host(ClockObserver):
    def __init__(self, id, tx_link, rx_link, cc) -> None:
        self.id = id
        self.tx_link = tx_link
        self.rx_link = rx_link
        self.cc = cc
        self.ts_ms = 0
        self.next_send_ts_ms = 0
        self.pacing_rate_bytes_per_sec = 15000

    def has_app_data(self):
        return True

    def get_pkt_to_send(self):
        return Packet(Packet.DATA_PKT, MSS)

    def send(self) -> None:
        while self.has_app_data() and self.cc.can_send() and self.ts_ms >= self.next_send_ts_ms:
            pkt = self.get_pkt_to_send()
            pkt.ts_sent_ms = self.ts_ms
            self.tx_link.push(pkt)
            self.cc.on_packet_sent(pkt)
            self.next_send_ts_ms += (MSS / self.pacing_rate_bytes_per_sec) * 1000

    def receive(self) -> None:
        pkt = self.rx_link.pull()
        while pkt is not None:
            print(self.id, self.ts_ms, pkt.pkt_type)
            if pkt.is_data_pkt():
                # TODO: send ack pkt
                ack_pkt = Packet(Packet.ACK_PKT, 80)
                ack_pkt.ts_sent_ms = self.ts_ms
                self.tx_link.push(ack_pkt)
            elif pkt.is_ack_pkt():
                self.cc.on_packet_acked(pkt)
            pkt = self.rx_link.pull()

    def tick(self, ts_ms) -> None:
        assert self.ts_ms <= ts_ms
        self.ts_ms = ts_ms
        self.send()
        self.receive()

    def reset(self) -> None:
        self.ts_ms = 0
        self.next_send_ts_ms = 0
        self.pacing_rate_bytes_per_sec = 15000
        self.cc.reset()
