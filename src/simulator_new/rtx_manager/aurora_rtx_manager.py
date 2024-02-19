import copy

from simulator_new.rtx_manager import RtxManager

class AuroraRtxManager(RtxManager):

    SRTT_ALPHA = 1 / 8
    SRTT_BETA = 1 / 4
    RTO_K = 4

    def __init__(self) -> None:
        super().__init__()

        self.unacked_buf = {}
        self.rtx_queue = set()
        self.max_lost_pkt_id = -1

        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.rto_ms = 3000

    def on_pkt_sent(self, pkt):
        if pkt.pkt_id not in self.unacked_buf:
            self.unacked_buf[pkt.pkt_id] = {
                "pkt": copy.deepcopy(pkt),
                "num_rtx": 0
            }

    def on_pkt_rcvd(self, ts_ms, pkt):
        if not pkt.is_ack_pkt():
            return

        if self.srtt_ms == 0 and self.rttvar_ms == 0:
            self.srtt_ms = pkt.rtt_ms()
            self.rttvar_ms = pkt.rtt_ms() / 2
        elif self.srtt_ms and self.rttvar_ms:
            self.srtt_ms = (1 - self.SRTT_ALPHA) * self.srtt_ms + \
                self.SRTT_ALPHA * pkt.rtt_ms()
            self.rttvar_ms = (1 - self.SRTT_BETA) * self.rttvar_ms + \
                self.SRTT_BETA * abs(self.srtt_ms - pkt.rtt_ms())
        else:
            raise ValueError("srtt and rttvar should be both 0 or both non-zeros.")
        self.rto_ms = max(1000, min(self.srtt_ms + self.RTO_K * self.rttvar_ms, 60000))

        if pkt.pkt_id in self.unacked_buf:
            self.unacked_buf.pop(pkt.pkt_id, None)
            for pkt_id in sorted(self.unacked_buf):
                unacked_pkt_info = self.unacked_buf[pkt_id]
                unacked_pkt = unacked_pkt_info['pkt']
                if pkt_id < pkt.pkt_id:
                    if pkt_id > self.max_lost_pkt_id:
                        self.on_pkt_lost(ts_ms, unacked_pkt)
                        self.max_lost_pkt_id = pkt_id

                    if (unacked_pkt_info['num_rtx'] == 0 or
                        ts_ms - unacked_pkt.ts_sent_ms > self.rto_ms):
                        unacked_pkt_info['num_rtx'] += 1
                        self.rtx_queue.add(pkt_id)
                else:
                    break

    def on_pkt_lost(self, ts_ms, pkt):
        if self.host:
            self.host.cc.on_pkt_lost(ts_ms, pkt)
            if self.host.recorder:
                self.host.recorder.on_pkt_lost(ts_ms, pkt)

    def peek_pkt(self):
        return self.unacked_buf[min(self.rtx_queue)]['pkt'].size_bytes if self.rtx_queue else 0

    def get_pkt(self):
        if self.rtx_queue:
            pkt_id = min(self.rtx_queue)
            pkt = self.unacked_buf[pkt_id]['pkt']
            self.rtx_queue.remove(pkt_id)
            return pkt
        else:
            return None

    def tick(self, ts_ms):
        pass
        # for pkt_id in sorted(self.unacked_buf):
        #     if pkt_id > self.max_lost_pkt_id:
        #         break
        #     unacked_pkt = self.unacked_buf[pkt_id]
        #     if (unacked_pkt.ts_sent_ms == unacked_pkt.ts_first_sent_ms or
        #         ts_ms - unacked_pkt.ts_sent_ms > self.rto_ms):
        #            self.rtx_queue.adnd(pkt_id)

    def reset(self):
        self.unacked_buf = {}
        self.rtx_queue = set()
        self.max_lost_id = -1
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.rto_ms = 3000
