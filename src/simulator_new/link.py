import random
from typing import Optional

from simulator_new.clock import ClockObserver
from simulator_new.trace import Trace

class Link(ClockObserver):
    def __init__(self, id, bw_trace: Optional[Trace] = None,
                 prop_delay_ms=25, queue_cap_bytes=-1,
                 pkt_loss_rate=0) -> None:
        self.id = id
        self.bw_trace = bw_trace
        self.prop_delay_ms = prop_delay_ms
        self.queue_cap_bytes = queue_cap_bytes
        self.queue_size_bytes = 0
        self.pkt_loss_rate = pkt_loss_rate
        self.ts_ms = 0
        self.queue = []
        self.ready_pkts = []
        self.budget_bytes = 0
        self.last_budget_update_ts_ms = 0
        self.host = None

    def register_host(self, host):
        self.host = host

    def push(self, pkt) -> None:
        """Push a packet onto the link"""
        if random.random() < self.pkt_loss_rate:
            return
        if self.queue_cap_bytes == -1 or \
            pkt.size_bytes + self.queue_size_bytes <= self.queue_cap_bytes:
            pkt.add_prop_delay_ms(self.prop_delay_ms)
            if self.bw_trace is None:
                self.ready_pkts.append(pkt)
            else:
                self.queue.append(pkt)
                self.queue_size_bytes += pkt.size_bytes
        else:
            assert self.host
            self.host.cc.on_pkt_lost(self.ts_ms, pkt)
        #     for i in range(len(self.queue)):
        #         print(self.queue[i].pkt_id, self.queue[i].ts_sent_ms, self.queue[i].delay_ms(), self.queue[i].ts_sent_ms + self.queue[i].delay_ms())
        #     print("drop", self.ts_ms, pkt.pkt_id,
        #           pkt.size_bytes + self.queue_size_bytes, self.queue_cap_bytes,
        #           pkt.app_data)

    def pull(self):
        """Pull a packet from the link"""
        # check pkt timestamp to determine whether to dequeue a pkt
        if self.ready_pkts and \
            self.ready_pkts[0].ts_sent_ms + self.ready_pkts[0].delay_ms() <= self.ts_ms:
            return self.ready_pkts.pop(0)
        return None

    def update_bw_budget(self):
        if not isinstance(self.bw_trace, Trace):
            return
        while self.queue:
            pkt = self.queue[0]
            prev_ts_ms = max(pkt.ts_sent_ms, self.last_budget_update_ts_ms)
            delta = int(self.bw_trace.get_avail_bits2send(
                prev_ts_ms / 1000, self.ts_ms / 1000)) / 8
            if prev_ts_ms == pkt.ts_sent_ms:
                self.budget_bytes = delta
            else:
                self.budget_bytes += delta
            self.last_budget_update_ts_ms = self.ts_ms
            if self.budget_bytes >= pkt.size_bytes:
                self.budget_bytes -= pkt.size_bytes
                pkt.add_queue_delay_ms(self.ts_ms - pkt.ts_sent_ms)
                self.queue.pop(0)
                self.queue_size_bytes -= pkt.size_bytes
                self.ready_pkts.append(pkt)
            else:
                break

    def tick(self, ts_ms) -> None:
        assert ts_ms >= self.ts_ms
        if self.ts_ms == ts_ms:
            return
        self.ts_ms = ts_ms
        self.update_bw_budget()

    def reset(self) -> None:
        if isinstance(self.bw_trace, Trace):
            self.bw_trace.reset()
        self.ts_ms = 0
        self.queue = []
        self.queue_size_bytes = 0
        self.budget_bytes = 0
        self.last_budget_update_ts_ms = 0
        self.ready_pkts = []
