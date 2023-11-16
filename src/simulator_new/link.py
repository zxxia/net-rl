import random

from simulator_new.clock import ClockObserver

class Link(ClockObserver):
    def __init__(self, id, bw_trace, prop_delay_ms=25, queue_cap_bytes=-1,
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

    def pull(self):
        """Pull a packet from the link"""
        # check pkt timestamp to determine whether to dequeue a pkt
        if self.ready_pkts and \
            self.ready_pkts[0].ts_sent_ms + self.ready_pkts[0].delay_ms() <= self.ts_ms:
            return self.ready_pkts.pop(0)
        return None

    def update_bw_budget(self):
        while self.queue:
            pkt = self.queue[0]
            if self.last_budget_update_ts_ms <= pkt.ts_sent_ms:
                self.budget_bytes = self.bw_trace.get_avail_bits2send(
                    pkt.ts_sent_ms / 1000, self.ts_ms / 1000) / 8
            else:
                self.budget_bytes += self.bw_trace.get_avail_bits2send(
                    self.last_budget_update_ts_ms / 1000, self.ts_ms / 1000) / 8
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
        self.bw_trace.reset()
        self.ts_ms = 0
        self.queue = []
        self.queue_size_bytes = 0
        self.budget_bytes = 0
        self.last_budget_update_ts_ms = 0
        self.ready_pkts = []
