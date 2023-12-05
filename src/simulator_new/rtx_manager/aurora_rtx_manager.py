import copy

from simulator_new.rtx_manager import RtxManager

class AuroraRtxManager(RtxManager):

    def __init__(self) -> None:
        super().__init__()

        self.unacked_buf = {}
        self.rtx_buf = set()
        self.max_lost_pkt_id = -1
        self.timeout_ms = 100

    def on_pkt_sent(self, pkt):
        if pkt.pkt_id not in self.unacked_buf:
            self.unacked_buf[pkt.pkt_id] = copy.deepcopy(pkt)

    def on_pkt_acked(self, ts_ms, pkt):
        if pkt.pkt_id in self.unacked_buf:
            self.unacked_buf.pop(pkt.pkt_id, None)
            for pkt_id in sorted(self.unacked_buf):
                unacked_pkt = self.unacked_buf[pkt_id]
                if pkt_id < pkt.pkt_id:
                    if pkt_id > self.max_lost_pkt_id:
                        self.on_pkt_lost(ts_ms, unacked_pkt)
                        self.max_lost_pkt_id = pkt_id

                    if (unacked_pkt.ts_sent_ms == unacked_pkt.ts_first_sent_ms or
                        ts_ms - unacked_pkt.ts_sent_ms > self.timeout_ms):
                           self.rtx_buf.add(pkt_id)
                else:
                    break
        else:
            raise KeyError("An ack should match a unacked data pkt in buffer.")

    def on_pkt_lost(self, ts_ms, pkt):
        if self.host:
            self.host.cc.on_pkt_lost(ts_ms, pkt)
            if self.host.recorder:
                self.host.recorder.on_pkt_lost(ts_ms, pkt)

    def get_pkt(self):
        if self.rtx_buf:
            pkt_id = min(self.rtx_buf)
            pkt = self.unacked_buf[pkt_id]
            self.rtx_buf.remove(pkt_id)
            return pkt
        return None

    def tick(self, ts_ms):
        for pkt_id in sorted(self.unacked_buf):
            if pkt_id > self.max_lost_pkt_id:
                break
            unacked_pkt = self.unacked_buf[pkt_id]
            if (unacked_pkt.ts_sent_ms == unacked_pkt.ts_first_sent_ms or
                ts_ms - unacked_pkt.ts_sent_ms > self.timeout_ms):
                   self.rtx_buf.add(pkt_id)

    def reset(self):
        self.unacked_pkt = {}
        self.rtx_buf = set()
        self.max_lost_id = -1
