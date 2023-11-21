import pandas as pd

from simulator_new.app import Application
from simulator_new.constant import MSS


class Encoder(Application):
    def __init__(self, lookup_table_path) -> None:
        super().__init__()
        self.fps = 25
        self.frame_id = 0
        self.last_encode_ts_ms = -1
        self.table = pd.read_csv(lookup_table_path)
        self.nframes = max(self.table['frame_id']) - min(self.table['frame_id']) + 1
        self.pkt_queue = []  # assume data queue has infinite capacity

    def has_data(self) -> bool:
        return len(self.pkt_queue) > 0

    def _encode(self, ts_ms, target_bitrate_bytes_per_sec):
        target_fsize_bytes = target_bitrate_bytes_per_sec / self.fps
        # look up in AE table
        mask0 = self.table['frame_id'] == self.frame_id
        mask1 = self.table['size'] <= target_fsize_bytes
        mask = mask0 & mask1
        if len(self.table[mask]) == 0:
            idx = self.table[mask0]['size'].argsort().index[0]
        else:
            idx = (self.table[mask]['size'] - target_fsize_bytes).argsort().index[-1]

        frame_size_bytes = int(self.table['size'].loc[idx])
        frame_size_left_bytes = frame_size_bytes
        model_id = self.table['model_id'].loc[idx]
        # packetize and push into pkt_queue
        while frame_size_left_bytes > 0:
            pkt_size_bytes = min(frame_size_left_bytes, MSS)
            self.pkt_queue.append(
                {"pkt_size_bytes": pkt_size_bytes,
                 "frame_id": self.frame_id,
                 "frame_size_bytes": frame_size_bytes,
                 "model_id": model_id,
                 "frame_encode_ts_ms": ts_ms})
            frame_size_left_bytes -= pkt_size_bytes

    def deliver_pkt(self, pkt):
        return

    def tick(self, ts_ms):
        if ts_ms - self.last_encode_ts_ms > 1000 / self.fps:
            self.frame_id = (self.frame_id + 1) % self.nframes
            assert self.host is not None
            self._encode(ts_ms, self.host.pacing_rate_bytes_per_sec)
            self.last_encode_ts_ms = ts_ms

    def get_pkt(self):
        if self.pkt_queue:
            pkt = self.pkt_queue.pop(0)
            return pkt['pkt_size_bytes'], pkt
        return 0, {}

    def reset(self):
        self.frame_id = 0
        self.last_encode_ts_ms = -1
        self.pkt_queue = []


class Decoder(Application):
    def __init__(self, lookup_table_path) -> None:
        self.fps = 25
        self.last_decode_ts_ms = 0
        self.pkt_queue = []  # recvd packets wait in the queue to be decoded
        self.frame_id = 1
        self.table = pd.read_csv(lookup_table_path)
        self.nframes = max(self.table['frame_id']) - min(self.table['frame_id']) + 1

    def has_data(self) -> bool:
        return False

    def get_pkt(self):
        return 1500, {}

    def deliver_pkt(self, pkt):
        self.pkt_queue.append(pkt)

    def _decode(self):
        recvd_frame_size_bytes = 0
        model_id = 0
        frame_size_bytes = 0
        for pkt in self.pkt_queue:
            app_data = pkt.app_data
            if app_data["frame_id"] == self.frame_id:
                recvd_frame_size_bytes += pkt.size_bytes
                model_id = app_data['model_id']
                frame_size_bytes = app_data['frame_size_bytes']
        self.pkt_queue = [pkt for pkt in self.pkt_queue
                          if pkt.app_data['frame_id'] > self.frame_id]

        frame_loss_rate = recvd_frame_size_bytes / frame_size_bytes
        assert 0 <= frame_loss_rate <= 1
        rounded_frame_loss_rate = round(frame_loss_rate, 1)
        mask = (self.table['frame_id'] == self.frame_id) & \
                (self.table['model_id'] == model_id) & \
                (self.table['loss'] == rounded_frame_loss_rate)
        ssim = self.table[mask]['ssim']
        res = (self.frame_id, recvd_frame_size_bytes, frame_size_bytes, frame_loss_rate, model_id, ssim)
        self.frame_id = (self.frame_id + 1) % self.nframes
        return res

    def tick(self, ts_ms):
        if ts_ms - self.last_decode_ts_ms >= (1000 / self.fps):
            if self.pkt_queue:
                self._decode()
                self.last_decode_ts_ms = ts_ms

    def reset(self):
        self.frame_id = 1
        self.last_decode_ts_ms = 0
        self.pkt_queue = []
