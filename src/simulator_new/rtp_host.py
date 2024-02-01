from simulator_new.host import Host
from simulator_new.packet import RTPPacket

class RTPHost(Host):
    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        super().__init__(id, tx_link, rx_link, cc, rtx_mngr, app)
        self.rtcp_pkt_cnt = 0
        self.pkt_cls = RTPPacket
        self.ts_last_rtcp_report_ms = 0
        self.base_pkt_id = -1
        self.max_pkt_id = -1
        self.rcvd_pkt_cnt = 0
        self.last_rtcp_rcvd_pkt_cnt = 0
        self.last_rtcp_expected_pkt_cnt = 0

    def _on_pkt_rcvd(self, pkt):
        self.cc.on_pkt_rcvd(pkt)
        if pkt.is_rtp_pkt():
            if self.base_pkt_id == -1:
                self.base_pkt_id = pkt.pkt_id
            self.max_pkt_id = max(self.max_pkt_id, pkt.pkt_id)
            self.rcvd_pkt_cnt += 1

            self.app.deliver_pkt(pkt)
            if self.recorder:
                self.recorder.on_pkt_rcvd(self.ts_ms, pkt)

    def send_rtcp_report(self, ts_ms, estimated_rate_Bps):
        if self.base_pkt_id > -1 and self.max_pkt_id > -1:
            expected_pkt_cnt = self.max_pkt_id - self.base_pkt_id + 1
        else:
            expected_pkt_cnt = 0
        if expected_pkt_cnt == self.last_rtcp_expected_pkt_cnt:
            loss_fraction = 0
        else:
            loss_fraction = 1 - max((self.rcvd_pkt_cnt - self.last_rtcp_rcvd_pkt_cnt) / \
                    (expected_pkt_cnt - self.last_rtcp_expected_pkt_cnt), 0)
        self.last_rtcp_rcvd_pkt_cnt = self.rcvd_pkt_cnt
        self.last_rtcp_expected_pkt_cnt = expected_pkt_cnt

        rtcp_report_pkt = RTPPacket(self.rtcp_pkt_cnt, RTPPacket.ACK_PKT, 1, app_data={})
        rtcp_report_pkt.estimated_rate_Bps = estimated_rate_Bps
        rtcp_report_pkt.loss_fraction = loss_fraction
        self.rtcp_pkt_cnt += 1
        rtcp_report_pkt.ts_sent_ms = self.ts_ms
        if rtcp_report_pkt.ts_first_sent_ms == 0:
            rtcp_report_pkt.ts_first_sent_ms = self.ts_ms
        self.ts_last_rtcp_report_ms = ts_ms
        self.tx_link.push(rtcp_report_pkt)

    def reset(self) -> None:
        self.rtcp_pkt_cnt = 0
        self.last_rtcp_rcvd_pkt_cnt = 0
        self.ts_last_rtcp_report_ms = 0
        self.base_pkt_id = -1
        self.max_pkt_id = -1
        self.rcvd_pkt_cnt = 0
        super().reset()

    def tick(self, ts_ms) -> None:
        super().tick(ts_ms)
        if ts_ms - self.ts_last_rtcp_report_ms == 1000 and \
            self.cc.delay_based_controller.estimated_rate_Bps > 0:
            # send a REMB message back to sender
            self.send_rtcp_report(ts_ms, self.cc.delay_based_controller.estimated_rate_Bps)
