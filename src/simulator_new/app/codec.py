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

    def peek_pkt(self) -> int:
        return self.pkt_queue[0]['pkt_size_bytes'] if self.pkt_queue else 0

    def _encode(self, ts_ms, target_bitrate_Bps):
        target_fsize_bytes = target_bitrate_Bps / self.fps
        # look up in AE table
        mask0 = self.table['frame_id'] == (self.frame_id % self.nframes)
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
        pkt_sizes = []
        while frame_size_left_bytes > 0:
            pkt_size_bytes = min(frame_size_left_bytes, MSS)
            pkt_sizes.append(pkt_size_bytes)
            frame_size_left_bytes -= pkt_size_bytes

        for pkt_size_bytes in pkt_sizes:
            self.pkt_queue.append(
                {"pkt_size_bytes": pkt_size_bytes,
                 "num_pkts": len(pkt_sizes),
                 "frame_id": self.frame_id,
                 "frame_size_bytes": frame_size_bytes,
                 "model_id": model_id,
                 "frame_encode_ts_ms": ts_ms})

    def deliver_pkt(self, pkt):
        return

    def tick(self, ts_ms):
        if self.last_encode_ts_ms is None or ts_ms - self.last_encode_ts_ms >= 1000 / self.fps:
            assert self.host is not None
            self._encode(ts_ms, self.host.pacer.pacing_rate_Bps)
            self.last_encode_ts_ms = ts_ms
            self.frame_id += 1

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
        # recvd packets wait in the queue to be decoded
        self.pkt_queue = {}
        self.frame_id = 0
        self.table = load_lookup_table(lookup_table_path)
        self.nframes = self.table['frame_id'].max() - self.table['frame_id'].min() + 1
        self.save_dir = save_dir
        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            self.log_fname = os.path.join(self.save_dir, "decoder_log.csv")
            self.log_fh = open(self.log_fname, 'w', 1)
            self.csv_writer = csv.writer(self.log_fh, lineterminator='\n')
            self.csv_writer.writerow(
                ['timestamp_ms','frame_id', "model_id",
                 'recvd_frame_size_bytes', 'frame_size_bytes',
                 "frame_encode_ts_ms", "frame_decode_ts_ms",
                 "frame_loss_rate", "ssim"])
        else:
            self.log_fname = None
            self.log_fh = None
            self.csv_writer = None

    def __del__(self):
        if self.log_fh:
            self.log_fh.close()

    def peek_pkt(self):
        return 0

    def get_pkt(self):
        return MSS, {}

    def deliver_pkt(self, pkt):
        frame_id = pkt.app_data['frame_id']
        frame_info = self.pkt_queue.get(
            frame_id, {"recvd_frame_size_bytes": 0, "frame_size_bytes": 0,
                       "num_pkts_recvd": 0, "num_pkts": 0,
                       "model_id": 0, "frame_encode_ts_ms": None,
                       "pkt_id_recvd": set(), "first_pkt_rcv_ts_ms": None,
                       "last_pkt_rcv_ts_ms": None})
        if pkt.pkt_id in frame_info['pkt_id_recvd']:
            return
        frame_info['pkt_id_recvd'].add(pkt.pkt_id)
        frame_info['recvd_frame_size_bytes'] += pkt.size_bytes
        frame_info['frame_size_bytes'] = pkt.app_data['frame_size_bytes']
        frame_info['num_pkts_recvd'] += 1
        frame_info['num_pkts'] = pkt.app_data['num_pkts']
        frame_info['model_id'] = pkt.app_data['model_id']
        frame_info['frame_encode_ts_ms'] = pkt.app_data['frame_encode_ts_ms']
        if frame_info['first_pkt_rcv_ts_ms'] is None:
            frame_info['first_pkt_rcv_ts_ms'] = pkt.ts_rcvd_ms
        frame_info['last_pkt_rcv_ts_ms'] = pkt.ts_rcvd_ms
        self.pkt_queue[frame_id] = frame_info

    def _decode(self, ts_ms):
        frame_info = self.pkt_queue[self.frame_id]
        recvd_frame_size_bytes = frame_info['recvd_frame_size_bytes']
        model_id = frame_info['model_id']
        frame_size_bytes = frame_info['frame_size_bytes']
        frame_encode_ts_ms = frame_info['frame_encode_ts_ms']
        if frame_size_bytes == 0:
            # no packet received at moment of decoding
            frame_loss_rate = 1
        else:
            frame_loss_rate = 1 - recvd_frame_size_bytes / frame_size_bytes
        assert 0 <= frame_loss_rate <= 1
        rounded_frame_loss_rate = round(frame_loss_rate, 1)
        mask = (self.table['frame_id'] == self.frame_id % self.nframes) & \
                (self.table['model_id'] == model_id) & \
                (self.table['loss'] == rounded_frame_loss_rate)

        if len(self.table[mask]['ssim']) >= 1:
            ssim = self.table[mask]['ssim'].iloc[0]
        else:
            ssim = -1
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, self.frame_id, model_id, recvd_frame_size_bytes,
                 frame_size_bytes, frame_encode_ts_ms, ts_ms, frame_loss_rate,
                 ssim])

        if self.frame_id - 1 in self.pkt_queue:
            prev_frame_info = self.pkt_queue[self.frame_id - 1]
            prev_frame_first_pkt_rcv_ts_ms = prev_frame_info['first_pkt_rcv_ts_ms']
            prev_frame_last_pkt_rcv_ts_ms = prev_frame_info['last_pkt_rcv_ts_ms']
        else:
            prev_frame_first_pkt_rcv_ts_ms = None
            prev_frame_last_pkt_rcv_ts_ms = None
        cur_frame_first_pkt_rcv_ts_ms = frame_info['first_pkt_rcv_ts_ms']
        cur_frame_last_pkt_rcv_ts_ms = frame_info['last_pkt_rcv_ts_ms']
        if self.host is not None and hasattr(self.host.cc, 'on_frame_rcvd'):
            self.host.cc.on_frame_rcvd(ts_ms, cur_frame_first_pkt_rcv_ts_ms,
                                       cur_frame_last_pkt_rcv_ts_ms,
                                       prev_frame_first_pkt_rcv_ts_ms,
                                       prev_frame_last_pkt_rcv_ts_ms)
        self.pkt_queue.pop(self.frame_id - 2, None)

    def tick(self, ts_ms):
            # only start to decode the 1st frame after completely received
        if self.frame_id in self.pkt_queue:
            frame_info = self.pkt_queue[self.frame_id]
            if self.frame_id == 0:
                # decode the other frames as long as there is 1 pkt recvd
                should_decode = (frame_info['recvd_frame_size_bytes'] ==
                                 frame_info['frame_size_bytes']) and (
                                 frame_info['num_pkts_recvd'] ==
                                 frame_info['num_pkts'])
            else:
                # TODO: double check decode condition for other frames
                should_decode = ts_ms - self.last_decode_ts_ms >= (1000 / self.fps) \
                    and frame_info['num_pkts_recvd'] >= 1
        else:
            should_decode = False
        if should_decode:
            self._decode(ts_ms)
            self.last_decode_ts_ms = ts_ms
            self.frame_id += 1

    def reset(self):
        self.frame_id = 0
        self.last_decode_ts_ms = None
        self.pkt_queue = {}
