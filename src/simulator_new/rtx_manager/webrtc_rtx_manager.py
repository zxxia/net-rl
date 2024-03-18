import copy

from simulator_new.rtx_manager import RtxManager

class WebRtcRtxManager(RtxManager):

    def __init__(self) -> None:
        super().__init__()
        self.pkt_buf = dict()
        self.rtx_queue = set()

    def register_host(self, host):
        self.host = host

    def on_pkt_sent(self, pkt):
        if pkt.app_data.get('padding', 0):
            return
        if pkt.pkt_id not in self.pkt_buf:
            self.pkt_buf[pkt.pkt_id] = {
                "pkt": None,
                "num_rtx": 0
            }
        self.pkt_buf[pkt.pkt_id]['pkt'] = copy.deepcopy(pkt)

    def on_pkt_rcvd(self, ts_ms, pkt):
        if not pkt.is_nack_pkt():
            return
        if pkt.pkt_id in self.pkt_buf:
            nacked_pkt_info = self.pkt_buf[pkt.pkt_id]
            nacked_pkt_info['num_rtx'] += 1
            self.rtx_queue.add(pkt.pkt_id)

    def peek_pkt(self):
        return self.pkt_buf[min(self.rtx_queue)]['pkt'].size_bytes if self.rtx_queue else 0

    def get_pkt(self):
        if self.rtx_queue:
            pkt_id = min(self.rtx_queue)
            pkt = self.pkt_buf[pkt_id]['pkt']
            self.rtx_queue.remove(pkt_id)
            return pkt
        return None

    def tick(self, ts_ms):
        # clean the pkt buffer
        for pkt_id in sorted(self.pkt_buf.copy()):
        #     # TODO: 20000 or 1000
            if ts_ms - self.pkt_buf[pkt_id]['pkt'].ts_first_sent_ms > 20000:
                del self.pkt_buf[pkt_id]
            else:
                break

    def reset(self):
        self.pkt_buf = dict()
        self.rtx_queue = set()
