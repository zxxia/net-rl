import copy
from simulator_new.cc.gcc.gcc import GCC

from simulator_new.host import Host
from simulator_new.packet import RTPPacket

RTCP_INTERVAL_MS = 50
REMB_INTERVAL_MS = 1000

class NackModule:
    def __init__(self) -> None:
        self.pkts_lost = dict()

    def on_pkt_rcvd(self, pkt, max_pkt_id):
        delete_pkt_id = self.pkts_lost.pop(pkt.pkt_id, None)
        # if delete_pkt_id:
        #     print("nackmoudle: pop", delete_pkt_id, max_pkt_id)
        # print('nack_module rcvd', pkt.pkt_id, max_pkt_id)
        if pkt.pkt_id < max_pkt_id:  # out-of-order or rtx
            return
        self._add_missing(max_pkt_id + 1, pkt.pkt_id)

    def _add_missing(self, from_pkt_id, to_pkt_id):
        for pkt_id in range(from_pkt_id, to_pkt_id):
            self.pkts_lost[pkt_id] = {"num_retries": 0, "ts_sent_ms": 0}

    def generate_nack(self, max_pkt_id):
        nacks = []
        for pkt_id in sorted(self.pkts_lost):
            info = self.pkts_lost[pkt_id]
            if info['num_retries'] > 10:
                self.pkts_lost.pop(pkt_id)
            if pkt_id < max_pkt_id:
                nacks.append(pkt_id)
        return nacks

    def on_nack_sent(self, ts_ms, pkt_id):
        if pkt_id in self.pkts_lost:
            self.pkts_lost[pkt_id]['num_retries'] += 1
            self.pkts_lost[pkt_id]['ts_sent_ms'] = ts_ms

    def cleanup_to(self, max_pkt_id):
        copied_keys = copy.copy(list(self.pkts_lost.keys()))
        for pkt_id in sorted(copied_keys):
            if pkt_id < max_pkt_id:
                self.pkts_lost.pop(pkt_id)

    def reset(self):
        self.pkts_lost = dict()


class RTPHost(Host):
    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app, save_dir=None) -> None:
        super().__init__(id, tx_link, rx_link, cc, rtx_mngr, app, save_dir)
        self.rtcp_pkt_cnt = 0
        self.pkt_cls = RTPPacket
        self.ts_last_rtcp_report_ms = 0
        self.ts_last_remb_ms = 0
        self.base_pkt_id = -1
        self.max_pkt_id = -1
        self.rcvd_pkt_cnt = 0
        self.rcvd_bytes = 0
        self.rcvd_bytes_prior = 0
        self.last_rtcp_rcvd_pkt_cnt = 0
        self.last_rtcp_expected_pkt_cnt = 0
        self.nack_module = NackModule()
        self.ts_last_full_nack_sent_ms = None
        self.pkt_id_last_nack_sent = -1
        self.owd_ms = 0
        self.delay_interval_ms = 0

        self.probe_info = {}

    def on_frame_rcvd(self, max_pkt_id):
        self.nack_module.cleanup_to(max_pkt_id)

    def _on_pkt_rcvd(self, pkt):
        # print(f'rtp_host {self.id} rcvd', self.ts_ms, pkt.pkt_id, pkt.app_data)
        self.cc.on_pkt_rcvd(self.ts_ms, pkt)
        if self.rtx_mngr:
            self.rtx_mngr.on_pkt_rcvd(self.ts_ms, pkt)
        if pkt.is_rtp_pkt():
            if self.base_pkt_id == -1:
                self.base_pkt_id = pkt.pkt_id
            self.nack_module.on_pkt_rcvd(pkt, self.max_pkt_id)
            self.max_pkt_id = max(self.max_pkt_id, pkt.pkt_id)
            self.rcvd_pkt_cnt += int(pkt.ts_first_sent_ms == pkt.ts_sent_ms)

            self.rcvd_bytes += pkt.size_bytes
            if self.owd_ms == 0:
                self.owd_ms = pkt.delay_ms()
            else:
                self.owd_ms = self.owd_ms * (1.0 - 1/8) + pkt.delay_ms() * 1/8
            jitter = (pkt.ts_rcvd_ms - pkt.ts_prev_pkt_rcvd_ms) \
                    - (pkt.ts_sent_ms - pkt.ts_prev_pkt_sent_ms)
            self.delay_interval_ms = self.delay_interval_ms + (abs(jitter) - self.delay_interval_ms) / 16
            self.app.deliver_pkt(pkt)
            pkt_ids = self.nack_module.generate_nack(self.max_pkt_id)
            self.send_nack(pkt_ids)
            if self.recorder:
                self.recorder.on_pkt_rcvd(self.ts_ms, pkt)
            if pkt.app_data.get('probe', 0):
                probe_cluster_id = pkt.app_data.get('probe_cluster_id', -1)
                # if self.probe_info['probe_cluster_id'] != probe_cluster_id:
                if probe_cluster_id not in self.probe_info:
                    self.probe_info[probe_cluster_id] = {"num_probe_pkts": 0,
                                       "tot_size_byte": 0,
                                       "first_pkt_sent_ts_ms": 0,
                                       "last_pkt_sent_ts_ms": 0,
                                       "first_pkt_rcvd_ts_ms": 0,
                                       "last_pkt_rcvd_ts_ms": 0,
                                       "last_pkt_sent_size_byte": 0,
                                       "first_pkt_rcvd_size_byte": 0,
                                       "probe_cluster_id": probe_cluster_id,
                                       "probe_rate_Bps": 0}
                    self.probe_info[probe_cluster_id]["probe_rate_Bps"] = pkt.pacing_rate_Bps
                    self.probe_info[probe_cluster_id]["first_pkt_sent_ts_ms"] = pkt.ts_sent_ms
                    self.probe_info[probe_cluster_id]["first_pkt_rcvd_ts_ms"] = pkt.ts_rcvd_ms
                    self.probe_info[probe_cluster_id]["first_pkt_rcvd_size_byte"] = pkt.size_bytes
                self.probe_info[probe_cluster_id]["num_probe_pkts"] += 1
                self.probe_info[probe_cluster_id]["tot_size_byte"] += pkt.size_bytes
                self.probe_info[probe_cluster_id]["last_pkt_sent_ts_ms"] = pkt.ts_sent_ms
                self.probe_info[probe_cluster_id]["last_pkt_rcvd_ts_ms"] = pkt.ts_rcvd_ms
                self.probe_info[probe_cluster_id]["last_pkt_sent_size_byte"] = pkt.size_bytes
        elif pkt.is_nack_pkt():
            if self.recorder:
                self.recorder.on_pkt_nack(self.ts_ms, pkt)
            # print(f"receive nack {pkt.pkt_id}")

    def send_nack(self, pkt_ids):
        # TODO: fix RTT
        RTT = 100
        filtered_pkt_ids = pkt_ids
        if self.ts_last_full_nack_sent_ms and self.ts_ms - self.ts_last_full_nack_sent_ms < 1.5 * RTT:
            return
        #     filtered_pkt_ids = [pkt_id for pkt_id in pkt_ids if pkt_id > self.pkt_id_last_nack_sent]

        for pkt_id in filtered_pkt_ids:
            nack = RTPPacket(pkt_id, RTPPacket.NACK_PKT, 1, app_data={})
            nack.ts_sent_ms = self.ts_ms
            if nack.ts_first_sent_ms == 0:
                nack.ts_first_sent_ms = self.ts_ms
            # self.pkt_id_last_nack_sent = pkt_id
            # print("send nack", self.ts_ms, pkt_id)
            self.tx_link.push(nack)
            self.nack_module.on_nack_sent(self.ts_ms, pkt_id)
        self.ts_last_full_nack_sent_ms = self.ts_ms

    def send_rtcp_report(self, ts_ms, estimated_rate_Bps):
        if self.base_pkt_id > -1 and self.max_pkt_id > -1:
            expected_pkt_cnt = self.max_pkt_id - self.base_pkt_id + 1
        else:
            expected_pkt_cnt = 0

        expected_pkt_cnt_interval = expected_pkt_cnt - self.last_rtcp_expected_pkt_cnt
        self.last_rtcp_expected_pkt_cnt = expected_pkt_cnt

        rcvd_pkt_cnt_interval = self.rcvd_pkt_cnt - self.last_rtcp_rcvd_pkt_cnt
        self.last_rtcp_rcvd_pkt_cnt = self.rcvd_pkt_cnt

        lost_pkt_cnt_interval = expected_pkt_cnt_interval - rcvd_pkt_cnt_interval

        if expected_pkt_cnt_interval == 0 or lost_pkt_cnt_interval <= 0:
            loss_fraction = 0
        else:
            loss_fraction = lost_pkt_cnt_interval / expected_pkt_cnt_interval

        rtcp_report_pkt = RTPPacket(self.rtcp_pkt_cnt, RTPPacket.ACK_PKT, 1, app_data={})
        rtcp_report_pkt.estimated_rate_Bps = estimated_rate_Bps
        rtcp_report_pkt.loss_fraction = loss_fraction
        rtcp_report_pkt.tput_Bps = (self.rcvd_bytes - self.rcvd_bytes_prior) * 1000 / RTCP_INTERVAL_MS
        rtcp_report_pkt.owd_ms = self.owd_ms
        rtcp_report_pkt.delay_interval_ms = self.delay_interval_ms
        self.rtcp_pkt_cnt += 1
        rtcp_report_pkt.ts_sent_ms = self.ts_ms
        if rtcp_report_pkt.ts_first_sent_ms == 0:
            rtcp_report_pkt.ts_first_sent_ms = self.ts_ms
        # if self.probe_info['probe_cluster_id'] != -1:
        #     rtcp_report_pkt.probe_info = copy.copy(self.probe_info)
        #     self.probe_info['probe_cluster_id'] = -1
        self.rcvd_bytes_prior = self.rcvd_bytes
        target_probe_cluster_id = -1
        for probe_cluster_id in sorted(self.probe_info, reverse=True):
            if self.probe_info[probe_cluster_id]['num_probe_pkts'] > 3:
                rtcp_report_pkt.probe_info = copy.copy(self.probe_info[probe_cluster_id])
                target_probe_cluster_id = probe_cluster_id
                break
        if self.probe_info:
            for probe_cluster_id in range(min(self.probe_info), target_probe_cluster_id + 1):
                self.probe_info.pop(probe_cluster_id)
        self.ts_last_rtcp_report_ms = ts_ms
        if estimated_rate_Bps > 0:
            self.ts_last_remb_ms = ts_ms
        self.tx_link.push(rtcp_report_pkt)
        self.cc.on_pkt_sent(ts_ms, rtcp_report_pkt)

    def reset(self) -> None:
        self.rtcp_pkt_cnt = 0
        self.last_rtcp_rcvd_pkt_cnt = 0
        self.ts_last_rtcp_report_ms = 0
        self.ts_last_remb_ms = 0
        self.base_pkt_id = -1
        self.max_pkt_id = -1
        self.rcvd_pkt_cnt = 0
        self.rcvd_bytes = 0
        self.rcvd_bytes_prior = 0
        self.owd_ms = 0
        self.delay_interval_ms = 0
        self.nack_module.reset()
        self.ts_last_full_nack_sent_ms = None
        self.pkt_id_last_nack_sent = -1
        super().reset()

    def tick(self, ts_ms) -> None:
        super().tick(ts_ms)
        if self.id == 1 and ts_ms - self.ts_last_rtcp_report_ms >= RTCP_INTERVAL_MS:
            if ts_ms - self.ts_last_remb_ms >= REMB_INTERVAL_MS and isinstance(self.cc, GCC):
                remb_rate_Bps = self.cc.delay_based_controller.remote_rate_controller.get_rate_Bps()
            else:
                remb_rate_Bps = -1
            # send a REMB message back to sender
            self.send_rtcp_report(ts_ms, remb_rate_Bps)
