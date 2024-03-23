def estimate_probed_rate_Bps(probe_info):
    send_interval_ms =  probe_info["last_pkt_sent_ts_ms"] - probe_info["first_pkt_sent_ts_ms"]
    send_size_byte = probe_info['tot_size_byte'] - probe_info['last_pkt_sent_size_byte']
    send_rate_Bps = send_size_byte * 1000 / send_interval_ms

    rcv_interval_ms =  probe_info["last_pkt_rcvd_ts_ms"] - probe_info["first_pkt_rcvd_ts_ms"]
    rcv_size_byte = probe_info['tot_size_byte'] - probe_info['first_pkt_rcvd_ts_ms']
    rcv_rate_Bps = rcv_size_byte * 1000 / rcv_interval_ms

    est_rate_Bps = min(send_rate_Bps, rcv_rate_Bps)

    # print("est_rate {:.3f}Mbps, send rate {:.3f}Mbps, rcv rate {:.3f}Mbps".format(
    #     est_rate_Bps * 8e-6, send_rate_Bps * 8e-6, rcv_rate_Bps* 8e-6))
    return est_rate_Bps


class ProbeController:
    # state
    INIT = 0
    WAIT_PROBE_RESULT = 1
    PROBE_DONE = 2

    INITIAL_EXP_PROBE = 0
    PERIODIC_PROBE = 1

    MIN_PROBE_PACKETS_SENT = 5
    MIN_PROBE_DURATION_MS = 15

    PROBE_PERIOD_MS = 50000

    def __init__(self, init_pacing_rate_Bps=0) -> None:
        self.init_pacing_rate_Bps = init_pacing_rate_Bps
        self.state = self.INIT
        # self.state = self.INITIAL_EXP_PROBE
        self.probe_rate_Bps = init_pacing_rate_Bps * 3
        self.initial_probe_round = 0
        self.probe_start_ts_ms = 0
        self.enabled = True

        self.probe_pkt_cnt = 0

        self.probe_cluster_id = 0

    def set_pacing_rate_Bps(self, init_pacing_rate_Bps):
        # called after __init__ and reset()
        self.init_pacing_rate_Bps = init_pacing_rate_Bps
        self.probe_rate_Bps = init_pacing_rate_Bps * 3

    def on_pkt_sent(self, ts_ms):
        self.probe_pkt_cnt += 1
        self._update_state(ts_ms)

    def _update_state(self, ts_ms):
        if self.enabled:
            self.enabled = not (ts_ms - self.probe_start_ts_ms > self.MIN_PROBE_DURATION_MS
                and self.probe_pkt_cnt > self.MIN_PROBE_PACKETS_SENT)
            # if self.enabled:
            #     self.state = self.WAIT_PROBE_RESULT

        if not self.enabled:
            self.probe_cluster_id += 1
            self.initial_probe_round += 1
            self.probe_pkt_cnt = 0
            if self.initial_probe_round < 2:
        #     if not self.enabled:
        #         self.enabled = True
                self.probe_rate_Bps = self.init_pacing_rate_Bps * 6
                self.probe_start_ts_ms = ts_ms
                self.enabled = True
        # else:
        #     self.state = self.PERIODIC_PROBE

    def is_enabled(self):
        return self.enabled

    def mark_pkt(self, pkt):
        pkt.app_data['probe'] = 1
        pkt.app_data['probe_cluster_id'] = self.probe_cluster_id

    def get_probe_rate_Bps(self):
        # print("probe rate", self.probe_rate_Bps * 8e-6, "Mbps")
        return self.probe_rate_Bps

    def set_estimated_rate_Bps(self, rate_Bps):
        pass

    def tick(self, ts_ms):
        self._update_state(ts_ms)

    def on_report(self, probe_info):
        send_interval_ms =  probe_info["last_pkt_sent_ts_ms"] - probe_info["first_pkt_sent_ts_ms"]
        send_size_byte = probe_info['tot_size_byte'] - probe_info['last_pkt_sent_size_byte']
        send_rate_Bps = send_size_byte * 1000 / send_interval_ms

        rcv_interval_ms =  probe_info["last_pkt_rcvd_ts_ms"] - probe_info["first_pkt_rcvd_ts_ms"]
        rcv_size_byte = probe_info['tot_size_byte'] - probe_info['first_pkt_rcvd_ts_ms']
        rcv_rate_Bps = rcv_size_byte * 1000 / rcv_interval_ms

        est_rate_Bps = min(send_rate_Bps, rcv_rate_Bps)

        print("est_rate {:.3f}Mbps, send rate {:.3f}Mbps, rcv rate {:.3f}Mbps".format(
            est_rate_Bps * 8e-6, send_rate_Bps * 8e-6, rcv_rate_Bps* 8e-6))
        return est_rate_Bps
