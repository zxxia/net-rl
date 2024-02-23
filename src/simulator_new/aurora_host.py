from simulator_new.host import Host
from simulator_new.packet import Packet

class AuroraHost(Host):

    def _on_pkt_rcvd(self, pkt):
        if pkt.is_data_pkt():
            self.app.deliver_pkt(pkt)
            if self.recorder:
                self.recorder.on_pkt_rcvd(self.ts_ms, pkt)
            # send ack pkt
            ack_pkt = self.pkt_cls(pkt.pkt_id, Packet.ACK_PKT, 80, {})
            ack_pkt.ts_sent_ms = self.ts_ms
            if ack_pkt.ts_first_sent_ms == 0:
                ack_pkt.ts_first_sent_ms = self.ts_ms
            ack_pkt.data_pkt_ts_sent_ms = pkt.ts_sent_ms
            ack_pkt.acked_size_bytes = pkt.size_bytes
            self.tx_link.push(ack_pkt)
        elif pkt.is_ack_pkt():
            data_pkt = self.rtx_mngr.unacked_buf[pkt.pkt_id] if self.rtx_mngr else None
            self.cc.on_pkt_acked(self.ts_ms, data_pkt, pkt)
            if self.rtx_mngr:
                self.rtx_mngr.on_pkt_rcvd(self.ts_ms, pkt)
            if self.recorder:
                self.recorder.on_pkt_acked(self.ts_ms, pkt)
        else:
            raise RuntimeError("Unsupported packet type.")
