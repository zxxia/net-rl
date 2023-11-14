import pandas as pd

from simulator.network_simulator.constants import BITS_PER_BYTE, BYTES_PER_PACKET

class Encoder:
    def __init__(self, lookup_table_path) -> None:
        self.fps = 25
        self.frame_id = 0
        self.frame_size_bytes = 0
        self.frame_size_left_bytes = 0
        self.model_id = -1
        self.last_encode_ts = -1
        self.table = pd.read_csv(lookup_table_path)
        self.nframes = max(self.table['frame_id']) - min(self.table['frame_id']) + 1

    def _encode(self, target_bitrate_bps):
        target_fsize_bytes = target_bitrate_bps / BITS_PER_BYTE / self.fps
        # look up in AE table
        mask0 = self.table['frame_id'] == self.frame_id
        mask1 = self.table['size'] <= target_fsize_bytes
        mask = mask0 & mask1
        if len(self.table[mask]) == 0:
            idx = self.table[mask0]['size'].argsort().index[0]
        else:
            idx = (self.table[mask]['size'] - target_fsize_bytes).argsort().index[-1]

        self.frame_size_bytes = int(self.table['size'].loc[idx])
        self.frame_size_left_bytes = self.frame_size_bytes
        self.model_id = self.table['model_id'].loc[idx]

    def get_pkt(self, ts, target_bitrate_bps):
        if ts - self.last_encode_ts > 1 / self.fps:
            self.frame_id = (self.frame_id + 1) % self.nframes
            self._encode(target_bitrate_bps)
            self.last_encode_ts = ts
        pkt_size_bytes = min(self.frame_size_left_bytes, BYTES_PER_PACKET)
        self.frame_size_left_bytes -= pkt_size_bytes
        return pkt_size_bytes, self.frame_id, self.model_id, self.frame_size_bytes

    def reset(self):
        self.frame_id = 0
        self.last_encode_ts = -1
        self.frame_size_bytes = 0
        self.frame_size_left_bytes = 0

class Decoder:
    def __init__(self, lookup_table_path) -> None:
        self.fps = 25
        self.last_decode_ts = 0
        self.pkts_to_decode = []
        self.frame_id = 1
        self.table = pd.read_csv(lookup_table_path)
        self.nframes = max(self.table['frame_id']) - min(self.table['frame_id']) + 1

    def deliver_pkt(self, ts, pkt):
        self.pkts_to_decode.append(pkt)
        if ts - self.last_decode_ts >= 1 / self.fps:
            self._decode()
            self.last_decode_ts = ts

    def _decode(self):
        recvd_frame_size_bytes = 0
        model_id = 0
        frame_size_bytes = 0
        for pkt in self.pkts_to_decode:
            if pkt.frame_id == self.frame_id:
                recvd_frame_size_bytes += pkt.pkt_size
                model_id = pkt.model_id
                frame_size_bytes = pkt.frame_size_bytes
        self.pkts_to_decode = [pkt for pkt in self.pkts_to_decode if pkt.frame_id > self.frame_id]

        frame_loss_rate = recvd_frame_size_bytes / frame_size_bytes
        assert 0 <= frame_loss_rate <= 1
        rounded_frame_loss_rate = round(frame_loss_rate, 1)
        mask = (self.table['frame_id'] == self.frame_id) & \
                (self.table['model_id'] == model_id) & \
                (self.table['loss'] == rounded_frame_loss_rate)
        ssim = self.table[mask]['ssim']
        res = (self.frame_id, recvd_frame_size_bytes, frame_size_bytes, frame_loss_rate, model_id, ssim)
        self.frame_id += 1
        return res

    def reset(self):
        self.frame_id = 1
        self.last_decode_ts = 0
        self.pkts_to_decode = []
