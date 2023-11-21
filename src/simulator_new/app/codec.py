import csv
import os

import pandas as pd

from simulator_new.app import Application
from simulator_new.constant import MSS

def load_lookup_table(lookup_table_path):
    table = pd.read_csv(lookup_table_path)
    if table['frame_id'].min() == 1:
        table['frame_id'] -= 1 # force 0-indexed frame id
    return table


class Encoder(Application):
    def __init__(self, lookup_table_path: str) -> None:
        super().__init__()
        self.fps = 25
        self.frame_id = 0
        self.last_encode_ts_ms = None
        self.table = load_lookup_table(lookup_table_path)
        self.nframes = self.table['frame_id'].max() - self.table['frame_id'].min() + 1
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
        if self.last_encode_ts_ms is None or ts_ms - self.last_encode_ts_ms >= 1000 / self.fps:
            assert self.host is not None
            self._encode(ts_ms, self.host.pacing_rate_bytes_per_sec)
            self.last_encode_ts_ms = ts_ms
            self.frame_id = (self.frame_id + 1) % self.nframes

    def get_pkt(self):
        if self.pkt_queue:
            pkt = self.pkt_queue.pop(0)
            return pkt['pkt_size_bytes'], pkt
        return 0, {}

    def reset(self):
        self.frame_id = 0
        self.last_encode_ts_ms = None
        self.pkt_queue = []


class Decoder(Application):
    def __init__(self, lookup_table_path: str, save_dir: str = "") -> None:
        self.fps = 25
        self.last_decode_ts_ms = None
        self.pkt_queue = []  # recvd packets wait in the queue to be decoded
        self.frame_id = 0
        self.table = load_lookup_table(lookup_table_path)
        self.nframes = self.table['frame_id'].max() - self.table['frame_id'].min() + 1
        self.save_dir = save_dir
        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            self.log_fh = open(os.path.join(self.save_dir, "decoder_log.csv"),
                               'w', 1)
            self.csv_writer = csv.writer(self.log_fh, lineterminator='\n')
            self.csv_writer.writerow(['frame_id', 'recvd_frame_size_bytes',
                                      'frame_size_bytes', "frame_loss_rate",
                                      "model_id", "ssim"])
        else:
            self.log_fh = None
            self.csv_writer = None

    def __del__(self):
        if self.log_fh:
            self.log_fh.close()

    def has_data(self) -> bool:
        return False

    def get_pkt(self):
        return MSS, {}

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
        if frame_size_bytes == 0:
            # no packet received at moment of decoding
            frame_loss_rate = 1
        else:
            frame_loss_rate = 1 - recvd_frame_size_bytes / frame_size_bytes
        assert 0 <= frame_loss_rate <= 1
        rounded_frame_loss_rate = round(frame_loss_rate, 1)
        mask = (self.table['frame_id'] == self.frame_id) & \
                (self.table['model_id'] == model_id) & \
                (self.table['loss'] == rounded_frame_loss_rate)

        if len(self.table[mask]['ssim']) >= 1:
            ssim = self.table[mask]['ssim'].iloc[0]
        else:
            ssim = -1
        if self.csv_writer:
            self.csv_writer.writerow(
                [self.frame_id, recvd_frame_size_bytes, frame_size_bytes,
                 frame_loss_rate, model_id, ssim])
        self.frame_id = (self.frame_id + 1) % self.nframes

    def tick(self, ts_ms):
        if self.last_decode_ts_ms is None:
            frame_ids = set()
            for pkt in self.pkt_queue:
                frame_ids.add(pkt.app_data['frame_id'])

            # only start to decode the 1st frame after it is received
            should_decode = len(frame_ids) >= 2
        else:
            should_decode = ts_ms - self.last_decode_ts_ms >= (1000 / self.fps)
        if should_decode:
            if self.pkt_queue:
                self._decode()
                self.last_decode_ts_ms = ts_ms

    def reset(self):
        self.frame_id = 0
        self.last_decode_ts_ms = None
        self.pkt_queue = []
