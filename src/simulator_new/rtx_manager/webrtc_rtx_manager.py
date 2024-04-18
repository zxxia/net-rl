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
        ret_size = 0
        if not self.rtx_queue:
            return ret_size
        pkts_to_rm = []
        for pkt_id in sorted(self.rtx_queue):
            if pkt_id not in self.pkt_buf:
                pkts_to_rm.append(pkt_id)
            else:
                ret_size = self.pkt_buf[pkt_id]['pkt'].size_bytes
                break
        for pkt_id in pkts_to_rm:
            self.rtx_queue.remove(pkt_id)
        return ret_size

    def get_pkt(self):
        if self.rtx_queue:
            pkt_id = min(self.rtx_queue)
            self.rtx_queue.remove(pkt_id)
            return self.get_buffered_pkt(pkt_id)
        return None

    def get_buffered_pkt(self, pkt_id):
        pkt_info = self.pkt_buf.get(pkt_id, None)
        return pkt_info['pkt'] if pkt_info else None

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
