# Assumptions in the flow level simulator
# 1. assume no queue in the network
# 2. assume data exceeding the bandwidth are dropped and treated as packet loss
# 3. assume frames are send out sequentially one by one
# 4. assume a frame has to be sent out within 1/fps seconds
# 5. assume no processing delays at sending and recving host

import csv
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator_new.trace import generate_trace

MODEL_ID_MAP = {64: 1, 128: 2, 256: 3, 512: 4, 1024: 5, 2048: 6, 4096: 7,
                6144: 8, 8192: 9, 12288: 10, 16384: 11}


def load_lookup_table(lookup_table_path):
    table = pd.read_csv(lookup_table_path)
    if table['frame_id'].min() == 1:
        table['frame_id'] -= 1 # force 0-indexed frame id
    return table


class Encoder:
    def __init__(self, lookup_table_path: str, fps: int) -> None:
        self.fps = fps
        self.table = load_lookup_table(lookup_table_path)
        self.nframes = self.table['frame_id'].max() - self.table['frame_id'].min() + 1

    def encode(self, frame_id, target_bitrate_Bps):
        target_fsize_byte = target_bitrate_Bps / self.fps
        # look up in AE table
        mask0 = self.table['frame_id'] == (frame_id % self.nframes)
        mask1 = self.table['size'] <= target_fsize_byte
        mask = mask0 & mask1
        if len(self.table[mask]) == 0:
            idx = self.table[mask0]['size'].argsort().index[0]
        else:
            idx = (self.table[mask]['size'] - target_fsize_byte).argsort().index[-1]

        frame_size_byte = int(self.table['size'].loc[idx])
        model_id = self.table['model_id'].loc[idx]

        return frame_size_byte, model_id


class Decoder:
    def __init__(self, lookup_table_path: str) -> None:
        self.table = load_lookup_table(lookup_table_path)
        self.nframes = self.table['frame_id'].max() - self.table['frame_id'].min() + 1

    def decode(self, frame_id, recvd_frame_size_byte, frame_size_byte, model_id):
        if frame_size_byte == 0:
            # no packet received at moment of decoding
            frame_loss_rate = 1
        else:
            frame_loss_rate = 1 - recvd_frame_size_byte / frame_size_byte
        assert 0 <= frame_loss_rate <= 1, f"{frame_loss_rate}, {recvd_frame_size_byte}, {frame_size_byte}"
        rounded_frame_loss_rate = round(frame_loss_rate, 1)
        mask = (self.table['frame_id'] == frame_id % self.nframes) & \
                (self.table['model_id'] == model_id) & \
                (self.table['loss'] == rounded_frame_loss_rate)

        if len(self.table[mask]['ssim']) >= 1:
            ssim = self.table[mask]['ssim'].iloc[0]
        else:
            ssim = -1
        return ssim, frame_loss_rate, rounded_frame_loss_rate


def plot(log_file, save_dir):
    df = pd.read_csv(log_file)
    inter_frame_gap_sec = df['ts_sec'].iloc[1] - df['ts_sec'].iloc[0]
    fig, axes = plt.subplots(3, 1, figsize=(6, 10))
    ax = axes[0]
    ax.plot(df['frame_id'], df['target_send_bitrate_kbps'], 'o-', c='C0', ms=2,
            label=f"target send rate, avg {df['target_send_bitrate_kbps'].mean():.3f}Kbps")
    ax.plot(df['frame_id'], df['send_bitrate_kbps'], 'o-', c='C1', ms=2,
            label=f"send rate, avg {df['send_bitrate_kbps'].mean():.3f}Kbps")
    ax.plot(df['frame_id'], df['recv_bitrate_kbps'], 'o-', c='C2', ms=2,
            label=f"recv rate, avg {df['recv_bitrate_kbps'].mean():.3f}Kbps")
    ax.plot(df['frame_id'], df['avg_bw_kbps'], 'o-', c='C3', ms=2,
            label=f"bw, avg {df['avg_bw_kbps'].mean():.3f}Kbps")
    ax.set_xlabel('Frame id')
    ax.set_xlim(0, )
    ax.set_ylim(0, )
    ax.set_ylabel('Bitrate (Kbps)')
    ax.legend()
    ax1_xticklabels = [tick * inter_frame_gap_sec for tick in ax.get_xticks()]
    ax1 = ax.twiny()
    ax1.set_xlabel('Time (sec)')
    ax1.set_xticks(ax.get_xticks())
    ax1.set_xbound(ax.get_xbound())
    ax1.set_xticklabels(ax1_xticklabels)

    ax = axes[1]
    ax.plot(df['frame_id'], df['ssim'], 'o-', c='C4', ms=2,
            label=f"ssim, avg {df['ssim'].mean():.3f}")
    ax.plot(df['frame_id'], df['frame_loss_rate'], 'o-', c='C5', ms=2,
            label=f"frame loss rate, avg {df['frame_loss_rate'].mean():.3f}")
    # ax.plot(df['frame_id'], df['rounded_frame_loss_rate'], 'o-', c='C5', ms=2,
    #         label=f"rounded frame loss rate, avg {df['rounded_frame_loss_rate'].mean():.3f}")
    ax.set_xlabel('Frame id')
    ax.set_xlim(0, )
    ax.set_ylabel('ssim')
    ax.set_ylim(0, 1)
    ax.legend()
    ax1_xticklabels = [tick * inter_frame_gap_sec for tick in ax.get_xticks()]
    ax1 = ax.twiny()
    ax1.set_xlabel('Time (sec)')
    ax1.set_xticks(ax.get_xticks())
    ax1.set_xbound(ax.get_xbound())
    ax1.set_xticklabels(ax1_xticklabels)
    ax2 = ax.twinx()
    ax2.set_ylabel('Frame loss rate')
    ax2.set_ylim(0, 1)

    ax = axes[2]
    model_ids = [MODEL_ID_MAP[val] for val in df["model_id"]]
    yticks = list(range(1, len(MODEL_ID_MAP)+1))
    yticklabels = [str(k) for k in sorted(MODEL_ID_MAP)]
    ax.plot(df['frame_id'], model_ids, 'o-', c='C6', ms=2)

    ax.set_xlabel('Frame id')
    ax.set_xlim(0, )
    ax.set_ylim(0, len(MODEL_ID_MAP) + 1)
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels)
    ax.set_ylabel('Autoencoder model id')
    ax1_xticklabels = [tick * inter_frame_gap_sec for tick in ax.get_xticks()]
    ax1 = ax.twiny()
    ax1.set_xlabel('Time (sec)')
    ax1.set_xticks(ax.get_xticks())
    ax1.set_xbound(ax.get_xbound())
    ax1.set_xticklabels(ax1_xticklabels)

    fig.tight_layout()
    fig.savefig(os.path.join(save_dir, 'flow_level_plot.jpg'),
                bbox_inches='tight')

class OracleBwEstimator:
    def __init__(self, trace) -> None:
        self.trace = trace

    def get_bw_bps(self, lo_ts_sec, up_ts_sec):
        assert up_ts_sec > lo_ts_sec
        return self.trace.get_avail_bits2send(lo_ts_sec, up_ts_sec) / \
                (up_ts_sec - lo_ts_sec)

class OracleBwEstimator1:
    def __init__(self, trace) -> None:
        self.trace = trace

    def get_bw_bps(self, lo_ts_sec, up_ts_sec):
        assert up_ts_sec > lo_ts_sec
        bps = self.trace.get_avail_bits2send(lo_ts_sec, up_ts_sec) / \
                (up_ts_sec - lo_ts_sec)
        return max(150*1e3, bps)

class ConstBwEstimator:
    def __init__(self, bw_kbps) -> None:
        self.bw_kbps = bw_kbps

    def get_bw_bps(self, lo_ts_sec, up_ts_sec):
        return self.bw_kbps * 1e3

def simulate():
    save_dir = "results/flow_level_simulator"
    lookup_table_path = "/home/zxxia/PhD/Projects/net-rl/AE_lookup_table/segment_3IY83M-m6is_480x360.mp4.csv"
    fps = 25
    trace = generate_trace(duration_range=(30, 30),
                           bandwidth_lower_bound_range=(0.02, 0.02),
                           bandwidth_upper_bound_range=(0.6, 0.6),
                           delay_range=(25, 25),
                           loss_rate_range=(0.0, 0.0),
                           queue_size_range=(20, 20),
                           T_s_range=(10, 10),
                           delay_noise_range=(0, 0), seed=32)

    t = np.arange(0, 30, 0.1)
    bw = np.ones_like(t) * 0.4

    bw[20:25] = 0.1

    trace.bandwidths = bw
    trace.timestamps = t
    trace.queue_size = 20
    bw_estimator = OracleBwEstimator(trace)
    # bw_estimator = OracleBwEstimator1(trace)
    # bw_estimator = ConstBwEstimator(120)
    encoder = Encoder(lookup_table_path, fps)
    decoder = Decoder(lookup_table_path)
    os.makedirs(save_dir, exist_ok=True)
    log_file = os.path.join(save_dir, "decoder_log.csv")
    with open(log_file, 'w', 1) as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(["ts_sec", "frame_id", "model_id", 'ssim',
                         "frame_size_byte", "recv_frame_size_byte",
                         "target_send_bitrate_kbps", "send_bitrate_kbps",
                         "recv_bitrate_kbps", "avg_bw_kbps", "frame_loss_rate",
                         "rounded_frame_loss_rate"])
        for frame_id in range(299):
            ts_sec = frame_id / fps

            target_bitrate_Bps = bw_estimator.get_bw_bps(
                ts_sec, ts_sec + 1/fps) / 8
            frame_size_byte, model_id = encoder.encode(
                frame_id, target_bitrate_Bps)
            avail_bytes = trace.get_avail_bits2send(ts_sec, ts_sec + 1/fps) / 8
            recv_frame_size_byte = min(avail_bytes, frame_size_byte)
            ssim, frame_loss_rate, rounded_frame_loss_rate = decoder.decode(
                frame_id, recv_frame_size_byte, frame_size_byte, model_id)
            avg_bw_kbps = avail_bytes * fps * 8 / 1e3
            send_bitrate_kbps = frame_size_byte * fps * 8 / 1e3
            recv_bitrate_kbps = recv_frame_size_byte * fps * 8 / 1e3
            writer.writerow([ts_sec, frame_id, model_id, ssim, frame_size_byte,
                             recv_frame_size_byte, target_bitrate_Bps * 8 / 1e3,
                             send_bitrate_kbps, recv_bitrate_kbps, avg_bw_kbps,
                             frame_loss_rate, rounded_frame_loss_rate])
    plot(log_file, save_dir)


if __name__ == '__main__':
    simulate()
