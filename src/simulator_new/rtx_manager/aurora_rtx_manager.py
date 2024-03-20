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

        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.rto_ms = 3000

        self.num_pkt_lost = 0

    def on_pkt_sent(self, pkt):
        if pkt.app_data.get('padding', 0):
            return
        if pkt.pkt_id not in self.unacked_buf:
            self.unacked_buf[pkt.pkt_id] = {
                "pkt": None,
                "num_rtx": 0,
                "rto_ms": self.rto_ms,
            }
        self.unacked_buf[pkt.pkt_id]['pkt'] = copy.deepcopy(pkt)

    def on_pkt_rcvd(self, ts_ms, pkt):
        if not pkt.is_ack_pkt():
            return

        # pkt is already acked and removed from buffer
        if pkt.pkt_id not in self.unacked_buf:
            return

        # remove the pkt from buffer
        self.unacked_buf.pop(pkt.pkt_id, None)

        if self.unacked_buf:
            for pkt_id in range(min(self.unacked_buf), pkt.pkt_id):
                if pkt_id not in self.unacked_buf:
                    continue
                pkt_info = self.unacked_buf[pkt_id]
                unacked_pkt = pkt_info['pkt']

                if (pkt_info['num_rtx'] == 0 or
                    ts_ms - unacked_pkt.ts_sent_ms > pkt_info["rto_ms"]) and \
                    pkt_id not in self.rtx_queue:
                    self.num_pkt_lost += 1
                    pkt_info['num_rtx'] += 1
                    # print(ts_ms, "rtx_manager lost:", pkt_id, ", num lost:",
                    #       self.num_pkt_lost, pkt_info['pkt'].ts_first_sent_ms,
                    #       pkt_info['pkt'].ts_sent_ms, self.rto_ms, self.rtx_queue)
                    self.on_pkt_lost(ts_ms, unacked_pkt)
                    self.rtx_queue.add(pkt_id)

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

    def on_pkt_lost(self, ts_ms, pkt):
        if self.host:
            self.host.cc.on_pkt_lost(ts_ms, pkt)
            if self.host.recorder:
                self.host.recorder.on_pkt_lost(ts_ms, pkt)

    def peek_pkt(self):
        ret_size = 0
        if not self.rtx_queue:
            return ret_size
        pkts_to_rm = []
        for pkt_id in sorted(self.rtx_queue):
            if pkt_id not in self.unacked_buf:
                pkts_to_rm.append(pkt_id)
            else:
                ret_size = self.unacked_buf[pkt_id]['pkt'].size_bytes
                break
        for pkt_id in pkts_to_rm:
            self.rtx_queue.remove(pkt_id)
        return ret_size

    def get_pkt(self):
        if self.rtx_queue:
            pkt_id = min(self.rtx_queue)
            pkt = self.unacked_buf[pkt_id]['pkt']
            self.rtx_queue.remove(pkt_id)
            return pkt
        else:
            return None

    def get_unacked_pkt(self, pkt_id):
        return self.unacked_buf.get(pkt_id, None)

    def tick(self, ts_ms):
        pass

    def reset(self):
        self.num_pkt_lost = 0
        self.unacked_buf = {}
        self.rtx_queue = set()
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.rto_ms = 3000
