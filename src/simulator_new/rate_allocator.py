class RateAllocator:

    def __init__(self, pacer, app, rtx_mngr) -> None:
        self.pacer = pacer
        self.app = app
        self.rtx_mngr = rtx_mngr

    def get_target_encode_bitrate_Bps(self):
        pacing_rate_Bps = self.pacer.pacing_rate_Bps
        rtx_qsize_bytes = 0
        for pkt_id in self.rtx_mngr.rtx_queue:
            pkt = self.rtx_mngr.get_buffered_pkt(pkt_id)
            if pkt:
                rtx_qsize_bytes += pkt.size_bytes
        app_qsize_bytes = sum([pkt["pkt_size_bytes"] for pkt in self.app.pkt_queue])
        pace_bytes = int(pacing_rate_Bps * self.pacer.pacing_rate_update_step_ms / 1000)
        encode_bytes = max(pace_bytes - rtx_qsize_bytes - app_qsize_bytes, 0)
        return encode_bytes * self.app.fps
