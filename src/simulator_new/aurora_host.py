from simulator_new.constant import MSS
from simulator_new.host import Host
from simulator_new.packet import Packet

class AuroraHost(Host):

    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app, save_dir=None) -> None:
        super().__init__(id, tx_link, rx_link, cc, rtx_mngr, app, save_dir)
        # self.pacer.max_budget_byte = 20 * MSS

    def _on_pkt_rcvd(self, pkt):
        self.cc.on_pkt_rcvd(self.ts_ms, pkt)
        if self.rtx_mngr:
            self.rtx_mngr.on_pkt_rcvd(self.ts_ms, pkt)
        if pkt.is_data_pkt():
            self.app.deliver_pkt(pkt)
            if self.recorder:
                self.recorder.on_pkt_rcvd(self.ts_ms, pkt)
            # send ack pkt
            app_data = {}
            if hasattr(self.app, 'frame_id') and \
               hasattr(self.app, 'frame_quality') and \
               hasattr(self.app, 'frame_delay_ms'):
                app_data = {'frame_id': self.app.frame_id,  # frame id to decode
                            'frame_delay_ms': self.app.frame_delay_ms,
                            'frame_quality': self.app.frame_quality}
            ack_pkt = self.pkt_cls(pkt.pkt_id, Packet.ACK_PKT, 80, app_data)
            ack_pkt.ts_sent_ms = self.ts_ms
            if ack_pkt.ts_first_sent_ms == 0:
                ack_pkt.ts_first_sent_ms = self.ts_ms
            ack_pkt.data_pkt_ts_sent_ms = pkt.ts_sent_ms
            ack_pkt.acked_size_bytes = pkt.size_bytes
            self.tx_link.push(ack_pkt)
        elif pkt.is_ack_pkt():
            if self.recorder:
                self.recorder.on_pkt_acked(self.ts_ms, pkt)
        else:
            raise RuntimeError("Unsupported packet type.")
