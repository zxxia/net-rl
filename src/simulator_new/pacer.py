import csv
import os

from simulator_new.constant import MSS

class Pacer:
    def __init__(self, host, max_budget_byte=2* MSS,
                 pacing_rate_update_step_ms=40, save_dir=None) -> None:
        self.host = host
        self.max_budget_byte = max_budget_byte
        self.pacing_rate_update_step_ms = pacing_rate_update_step_ms
        self.budget_byte = MSS
        self.ts_last_update_ms = 0
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            self.log_path = os.path.join(save_dir, 'pacer_log.csv')
            self.pacer_log = open(self.log_path, 'w', 1)
            self.csv_writer = csv.writer(self.pacer_log, lineterminator='\n')
            self.csv_writer.writerow(['timestamp_ms', "pacing_rate_Bps"])
        else:
            self.log_path = None
            self.pacer_log = None
            self.csv_writer = None
        self.set_pacing_rate_Bps(0, self.host.cc.get_est_rate_Bps(
            0, self.pacing_rate_update_step_ms))

    def __del__(self):
        if self.pacer_log:
            self.pacer_log.close()

    def set_pacing_rate_mbps(self, ts_ms, rate_mbps):
        self.set_pacing_rate_Bps(ts_ms, rate_mbps * 1e6 / 8)

    def set_pacing_rate_Bps(self, ts_ms, rate_Bps):
        self.pacing_rate_Bps = rate_Bps
        self.ts_last_pacing_rate_update_ms = ts_ms
        if self.csv_writer:
            self.csv_writer.writerow(
                [self.ts_last_pacing_rate_update_ms, self.pacing_rate_Bps])

    def can_send(self, pkt_size_byte):
        return pkt_size_byte <= self.budget_byte

    def on_pkt_sent(self, pkt_size_byte):
        assert pkt_size_byte <= self.budget_byte, f"{pkt_size_byte} {self.budget_byte}"
        self.budget_byte -= pkt_size_byte

    def tick(self, ts_ms):
        # update_budget
        elapsed_time_ms = ts_ms - self.ts_last_update_ms
        budget_inc = self.pacing_rate_Bps * elapsed_time_ms / 1000
        self.budget_byte = min(self.max_budget_byte, self.budget_byte + budget_inc)
        self.ts_last_update_ms = ts_ms

        if ts_ms - self.ts_last_pacing_rate_update_ms >= self.pacing_rate_update_step_ms:
            self.set_pacing_rate_Bps(ts_ms, self.host.cc.get_est_rate_Bps(
                ts_ms, ts_ms + self.pacing_rate_update_step_ms))

    def reset(self):
        self.budget_byte = MSS
        self.ts_last_update_ms = 0
        self.set_pacing_rate_Bps(0, self.host.cc.get_est_rate_Bps(
            0, self.pacing_rate_update_step_ms))
# pacer = Pacer(MSS * 10)
# pacer.set_pacing_rate_Bps(30000000)
# sent_bytes = 0
# for ts_ms in range(10*1000):
#     while pacer.can_send(MSS):
#         pacer.on_pkt_sent(MSS)
#         sent_bytes += MSS
#     pacer.tick(ts_ms)
#     print(pacer.budget_byte)
# print(sent_bytes / 10)
