import csv
import os

import pandas as pd

from simulator_new.app import Application
from simulator_new.constant import MSS

def load_lookup_table(lookup_table_path):
    table = pd.read_csv(lookup_table_path)
    table = table[table['frame_id'] != 0]
    if table['frame_id'].min() == 1:
        table['frame_id'] -= 1 # force 0-indexed frame id
    return table


def packetize(model_id, frame_id, frame_size_byte, encode_ts_ms,
              target_bitrate_Bps, padding_byte):
    n_pkts, remainder_byte = divmod(frame_size_byte, MSS)
    n_pkts = max(n_pkts + int(remainder_byte > 0), 5)
    base, extra = divmod(frame_size_byte, n_pkts)
    pkt_sizes = [base + (i < extra) for i in range(n_pkts)]

    pkts = []

    for pkt_size in pkt_sizes:
        assert pkt_size <= MSS
        pkts.append(
            {"pkt_size_bytes": pkt_size,
             "num_pkts": n_pkts,
             "frame_id": frame_id,
             "frame_size_bytes": frame_size_byte,
             "padding_bytes": padding_byte,
             "model_id": model_id,
             "frame_encode_ts_ms": encode_ts_ms,
             "target_bitrate_Bps": target_bitrate_Bps,
             "padding": 0})

    padding_pkts = []
    n_padding_pkts, remainder_padding_byte = divmod(padding_byte, MSS)

    for _ in range(int(n_padding_pkts)):
        padding_pkts.append(
            {"pkt_size_bytes": MSS,
             "num_pkts": n_pkts,
             "frame_id": frame_id,
             "frame_size_bytes": frame_size_byte,
             "padding_bytes": padding_byte,
             "model_id": model_id,
             "frame_encode_ts_ms": encode_ts_ms,
             "target_bitrate_Bps": target_bitrate_Bps,
             "padding": 1})
    if remainder_padding_byte:
        padding_pkts.append(
            {"pkt_size_bytes": remainder_padding_byte,
             "num_pkts": n_pkts,
             "frame_id": frame_id,
             "frame_size_bytes": frame_size_byte,
             "model_id": model_id,
             "frame_encode_ts_ms": encode_ts_ms,
             "target_bitrate_Bps": target_bitrate_Bps,
             "padding": 1})
    return pkts, padding_pkts


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

    def _encode(self, target_bitrate_Bps):
        target_fsize_bytes = int(target_bitrate_Bps / self.fps)
        # look up in AE table
        mask0 = self.table['frame_id'] == (self.frame_id % self.nframes)
        mask1 = self.table['size'] <= target_fsize_bytes
        mask = mask0 & mask1
        if len(self.table[mask]) == 0:
            idx = self.table[mask0]['size'].argsort().index[0]
        else:
            idx = (self.table[mask]['size'] - target_fsize_bytes).argsort().index[-1]

        frame_size_byte = int(self.table['size'].loc[idx])
        model_id = self.table['model_id'].loc[idx]

        return model_id, frame_size_byte, max(target_fsize_bytes - frame_size_byte, 0)

    def deliver_pkt(self, pkt):
        return

    def tick(self, ts_ms):
        if self.last_encode_ts_ms is None or ts_ms - self.last_encode_ts_ms >= 1000 / self.fps:
            assert self.host is not None and self.host.rate_allocator is not None
            target_bitrate_Bps = self.host.rate_allocator.get_target_encode_bitrate_Bps()
            model_id, frame_size_byte, padding_byte = self._encode(target_bitrate_Bps)
            pkts, padding_pkts = packetize(
                model_id, self.frame_id, frame_size_byte, ts_ms,
                target_bitrate_Bps, padding_byte)
            self.pkt_queue += pkts
            self.pkt_queue += padding_pkts
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
        self.first_decode_ts_ms = None
        # rcvd packets wait in the queue to be decoded
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
                ['frame_id', "model_id",
                 'rcvd_frame_size_bytes', 'frame_size_bytes',
                 "frame_encode_ts_ms", "frame_decode_ts_ms",
                 "frame_loss_rate", "ssim", 'target_bitrate_Bps'])
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
            frame_id, {"rcvd_frame_size_bytes": 0, "frame_size_bytes": 0,
                       "num_pkts_rcvd": 0, "num_pkts": 0,
                       "model_id": 0, "frame_encode_ts_ms": None,
                       "pkt_id_rcvd": set(), "last_pkt_sent_ts_ms": None,
                       "last_pkt_rcv_ts_ms": None, 'target_bitrate_Bps': 0,
                       "padding_bytes": 0, "num_padding_pkts_rcvd": 0})
        if pkt.pkt_id in frame_info['pkt_id_rcvd']:
            return
        frame_info['pkt_id_rcvd'].add(pkt.pkt_id)
        frame_info['frame_size_bytes'] = pkt.app_data['frame_size_bytes']
        frame_info['num_pkts'] = pkt.app_data['num_pkts']
        frame_info['model_id'] = pkt.app_data['model_id']
        frame_info['frame_encode_ts_ms'] = pkt.app_data['frame_encode_ts_ms']
        frame_info['target_bitrate_Bps'] = pkt.app_data['target_bitrate_Bps']
        if pkt.ts_sent_ms == pkt.ts_first_sent_ms:
            frame_info['last_pkt_sent_ts_ms'] = pkt.ts_sent_ms
            frame_info['last_pkt_rcv_ts_ms'] = pkt.ts_rcvd_ms
        if pkt.app_data['padding']:
            frame_info['padding_bytes'] += pkt.size_bytes
            frame_info['num_padding_pkts_rcvd'] += 1
        else:
            frame_info['rcvd_frame_size_bytes'] += pkt.size_bytes
            frame_info['num_pkts_rcvd'] += 1
        self.pkt_queue[frame_id] = frame_info

    def _decode(self, ts_ms):
        frame_info = self.pkt_queue[self.frame_id]
        rcvd_frame_size_bytes = frame_info['rcvd_frame_size_bytes']
        model_id = frame_info['model_id']
        frame_size_bytes = frame_info['frame_size_bytes']
        frame_encode_ts_ms = frame_info['frame_encode_ts_ms']
        target_bitrate_Bps = frame_info['target_bitrate_Bps']
        if frame_size_bytes == 0:
            # no packet received at moment of decoding
            frame_loss_rate = 1
        else:
            frame_loss_rate = 1 - rcvd_frame_size_bytes / frame_size_bytes
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
                [self.frame_id, model_id, rcvd_frame_size_bytes,
                 frame_size_bytes, frame_encode_ts_ms, ts_ms, frame_loss_rate,
                 ssim, target_bitrate_Bps])

        if self.frame_id - 1 in self.pkt_queue:
            prev_frame_info = self.pkt_queue[self.frame_id - 1]
            prev_frame_last_pkt_sent_ts_ms = prev_frame_info['last_pkt_sent_ts_ms']
            prev_frame_last_pkt_rcv_ts_ms = prev_frame_info['last_pkt_rcv_ts_ms']
        else:
            prev_frame_last_pkt_sent_ts_ms = None
            prev_frame_last_pkt_rcv_ts_ms = None
        frame_last_pkt_sent_ts_ms = frame_info['last_pkt_sent_ts_ms']
        frame_last_pkt_rcv_ts_ms = frame_info['last_pkt_rcv_ts_ms']
        if self.host is not None and hasattr(self.host.cc, 'on_frame_rcvd'):
            self.host.cc.on_frame_rcvd(ts_ms, frame_last_pkt_sent_ts_ms,
                                       frame_last_pkt_rcv_ts_ms,
                                       prev_frame_last_pkt_sent_ts_ms,
                                       prev_frame_last_pkt_rcv_ts_ms)
            self.host.on_frame_rcvd(max(frame_info['pkt_id_rcvd']))
        self.pkt_queue.pop(self.frame_id - 2, None)

    def tick(self, ts_ms):
        while True:
            if self.can_decode(ts_ms):
                self._decode(ts_ms)
                if self.first_decode_ts_ms is None:
                    self.first_decode_ts_ms = ts_ms
                self.last_decode_ts_ms = ts_ms
                self.frame_id += 1
            else:
                break

    def can_decode(self, ts_ms):
        if self.frame_id in self.pkt_queue:
            frame_info = self.pkt_queue[self.frame_id]
            if self.frame_id == 0:
                # decode the 1st frame only if it is completely received
                return (frame_info['rcvd_frame_size_bytes'] ==
                        frame_info['frame_size_bytes']) and (
                        frame_info['num_pkts_rcvd'] == frame_info['num_pkts'])
            else:
                # decode a frame as early as possible
                # return ts_ms - self.first_decode_ts_ms >= self.frame_id * 1000 / self.fps and \
                #     self.frame_id in self.pkt_queue and \
                #     frame_info['rcvd_frame_size_bytes'] / frame_info['frame_size_bytes'] >= 0.1

                # decode a frame as early as possible and at least one pkt for
                # the next frame is received
                return ts_ms - self.first_decode_ts_ms >= self.frame_id * 1000 / self.fps and \
                    self.frame_id in self.pkt_queue and self.frame_id + 1 in self.pkt_queue and \
                    frame_info['rcvd_frame_size_bytes'] / frame_info['frame_size_bytes'] >= 0.1

                # decode a frame only if the frame is completely received
                # return (ts_ms - self.first_decode_ts_ms >= self.frame_id * 1000 / self.fps) and \
                #         (frame_info['rcvd_frame_size_bytes'] == frame_info['frame_size_bytes']) \
                #         and (frame_info['num_pkts_rcvd'] == frame_info['num_pkts'])
        return False

    def reset(self):
        self.frame_id = 0
        self.last_decode_ts_ms = None
        self.first_decode_ts_ms = None
        self.pkt_queue = {}
