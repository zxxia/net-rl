from simulator_new.constant import MSS

class Pacer:
    def __init__(self, max_budget_byte=MSS) -> None:
        self.max_budget_byte = max_budget_byte
        self.budget_byte = max_budget_byte
        self.ts_last_update_ms = 0
        self.pacing_rate_Bps = 0

    def set_pacing_rate_mbps(self, rate_mbps):
        self.pacing_rate_Bps = rate_mbps * 1e6 / 8

    def set_pacing_rate_Bps(self, rate_Bps):
        self.pacing_rate_Bps = rate_Bps

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

    def reset(self):
        self.budget_byte = self.max_budget_byte
        self.ts_last_update_ms = 0
        self.pacing_rate_Bps = 0
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
