import os
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator_new.cc.pcc.aurora.aurora import pcc_aurora_reward
from simulator_new.constant import BITS_PER_BYTE, MSS
from simulator_new.stats_recorder import PacketLog
from simulator_new.trace import Trace


def plot_mi_log(trace: Optional[Trace], log_file: str, save_dir: str, cc: str):
    df = pd.read_csv(log_file)
    assert isinstance(df, pd.DataFrame)
    ts_sec = df['timestamp_ms'] / 1e3
    recv_rate_mbps = df['recv_rate_byte_per_sec'] * BITS_PER_BYTE / 1e6
    avg_recv_rate_mbps = recv_rate_mbps.mean()
    send_rate_mbps = df['send_rate_byte_per_sec'] * BITS_PER_BYTE / 1e6
    send_recv_rate_mbps = send_rate_mbps.mean()
    avg_lat_ms = df['latency_ms'].mean()
    avg_loss_ratio = df['loss_ratio'].mean()
    fig, axes = plt.subplots(6, 1, figsize=(12, 10))
    axes[0].set_title(cc)
    axes[0].plot(ts_sec, recv_rate_mbps, 'o-', ms=2,
                 label='throughput, avg {:.3f}mbps'.format(avg_recv_rate_mbps))
    axes[0].plot(ts_sec, send_rate_mbps, 'o-', ms=2,
                 label='send rate, avg {:.3f}mbps'.format(send_recv_rate_mbps))
    ts_max = ts_sec.iloc[-1]

    if trace:
        avg_bw = trace.avg_bw
        min_rtt = trace.min_delay * 2 / 1e3
        axes[0].plot(trace.timestamps, trace.bandwidths, 'o-', ms=2,
                     drawstyle='steps-post',
                     label='bw, avg {:.3f}mbps'.format(avg_bw))
        ts_max = min(ts_max, trace.timestamps[-1])
    else:
        axes[0].plot(ts_sec, df['bandwidth'] / 1e6,
                     label='bw, avg {:.3f}mbps'.format(df['bandwidth'].mean() / 1e6))
        avg_bw = df['bandwidth'].mean() / 1e6
        min_rtt = None
    axes[0].set_xlabel("Time(s)")
    axes[0].set_ylabel("mbps")
    axes[0].legend(loc='right')
    axes[0].set_ylim(0, )
    axes[0].set_xlim(0, ts_max)

    axes[1].plot(ts_sec, df['latency_ms'],
                 label='RTT avg {:.3f}ms'.format(avg_lat_ms))
    axes[1].set_xlabel("Time(s)")
    axes[1].set_ylabel("Latency(ms)")
    axes[1].legend(loc='right')
    axes[1].set_xlim(0, ts_max)
    axes[1].set_ylim(0, )

    axes[2].plot(ts_sec, df['loss_ratio'],
                 label='loss_ratio avg {:.3f}'.format(avg_loss_ratio))
    axes[2].set_xlabel("Time(s)")
    axes[2].set_ylabel("loss ratio")
    axes[2].legend()
    axes[2].set_xlim(0, ts_max)
    axes[2].set_ylim(0, 1)

    avg_reward_mi = pcc_aurora_reward(
            avg_recv_rate_mbps / BITS_PER_BYTE / MSS,
            avg_lat_ms / 1e3, avg_loss_ratio,
            avg_bw * 1e6 / BITS_PER_BYTE / MSS, min_rtt)

    axes[3].plot(ts_sec, df['reward'],
                 label='rewards avg {:.3f}'.format(avg_reward_mi))
    axes[3].set_xlabel("Time(s)")
    axes[3].set_ylabel("Reward")
    axes[3].legend()
    axes[3].set_xlim(0, ts_max)
    # axes[3].set_ylim(, )

    axes[4].plot(ts_sec, df['action'] * 1.0,
                 label='delta avg {:.3f}'.format(df['action'].mean()))
    axes[4].set_xlabel("Time(s)")
    axes[4].set_ylabel("delta")
    axes[4].legend()
    axes[4].set_xlim(0, ts_max)

    axes[5].plot(ts_sec, df['bytes_in_queue'] / df['queue_capacity_bytes'],
                 label='Queue Occupancy')
    axes[5].set_xlabel("Time(s)")
    axes[5].set_ylabel("Queue occupancy")
    axes[5].legend()
    axes[5].set_xlim(0, ts_max)
    axes[5].set_ylim(0, 1)

    plt.tight_layout()
    if save_dir is not None:
        fig.savefig(os.path.join(save_dir, "{}_time_series.jpg".format(cc)),
                    bbox_inches='tight')
    plt.close()


def plot_pkt_log(trace, log_file, save_dir, cc):
    pkt_log = PacketLog.from_log_file(log_file, 500)
    sending_rate_ts_sec, sending_rate_mbps = pkt_log.get_sending_rate_mbps()
    tput_ts_sec, tput_mbps = pkt_log.get_throughput_mbps()
    rtt_ts_sec, rtt_ms = pkt_log.get_rtt_ms()
    # queue_delay_ts, queue_delay = pkt_log.get_queue_delay()
    pkt_loss_rate = pkt_log.get_loss_rate()
    avg_tput_mbps = pkt_log.get_avg_throughput_mbps()
    avg_sending_rate_mbps = pkt_log.get_avg_sending_rate_mbps()
    avg_lat = pkt_log.get_avg_rtt_ms()
    # reward = pkt_log.get_reward("", None)
    # normalized_reward = pkt_log.get_reward("", trace)
    fig, axes = plt.subplots(2, 1, figsize=(6, 8))
    axes[0].plot(tput_ts_sec, tput_mbps, "-o", ms=2,  # drawstyle='steps-post',
                 label='throughput, avg {:.3f}Mbps'.format(avg_tput_mbps))
    axes[0].plot(sending_rate_ts_sec, sending_rate_mbps, "-o", ms=2,  # drawstyle='steps-post',
                 label='sending rate, avg {:.3f}Mbps'.format(avg_sending_rate_mbps))
    if trace is not None:
        axes[0].plot(trace.timestamps, trace.bandwidths, "-o", ms=2,  # drawstyle='steps-post',
                     label='bandwidth, avg {:.3f}Mbps'.format(np.mean(trace.bandwidths)))
        queue_size = trace.queue_size
        trace_random_loss = trace.loss_rate
        delay_noise = trace.delay_noise
    else:
        queue_size = "N/A"
        trace_random_loss = "N/A"
        delay_noise = "N/A"
        # axes[0].plot(np.arange(30), np.ones_like(np.arange(30)) * 6, "-o", ms=2,  # drawstyle='steps-post',
        #              label='bandwidth, avg {:.3f}Mbps'.format(6))
    ts_max = min([trace.timestamps[-1], sending_rate_ts_sec[-1], tput_ts_sec[-1]])
    axes[0].legend()
    axes[0].set_xlabel("Time(s)")
    axes[0].set_ylabel("Rate(Mbps)")
    axes[0].set_xlim(0, ts_max)
    axes[0].set_ylim(0, )
    # if trace is not None:
    #     axes[0].set_title('{} reward={:.3f}, normalized reward={:.3f}, gap={:.3f}'.format(
    #         cc, reward, normalized_reward, trace.optimal_reward - normalized_reward))
    # else:
    #     axes[0].set_title('{} reward={:.3f}, normalized reward={:.3f}'.format(
    #         cc, reward, normalized_reward))

    axes[1].plot(rtt_ts_sec, rtt_ms, ms=2, label='RTT, avg {:.3f}ms'.format(avg_lat))
    # axes[1].plot(queue_delay_ts, queue_delay, label='Queue delay, avg {:.3f}ms'.format(np.mean(queue_delay)))
    if trace is not None:
        axes[1].plot(rtt_ts_sec, np.ones_like(rtt_ms) * 2 * trace.min_delay, c='C2',
                     label="trace minRTT {:.3f}ms".format(2*min(trace.delays)))
    axes[1].legend()
    axes[1].set_xlabel("Time(s)")
    axes[1].set_ylabel("Latency(ms)")
    axes[1].set_title('{} loss={:.3f}, rand loss={:.3f}, queue={}, lat_noise={:.3f}'.format(
        cc, pkt_loss_rate, trace_random_loss, queue_size, delay_noise))
    axes[1].set_xlim(0, rtt_ts_sec[-1])
    # axes[1].set_ylim(0, )

    fig.tight_layout()
    if save_dir:
        fig.savefig(os.path.join(save_dir, '{}_pkt_log_plot.jpg'.format(cc)),
                    bbox_inches='tight')
    plt.close()

def plot_decoder_log(log_fname, save_dir, cc):
    df = pd.read_csv(log_fname)
    fig, axes = plt.subplots(3, 1, figsize=(6, 8))
    ax = axes[0]
    ax.plot(df['frame_id'], df['frame_loss_rate'], color='C0')
    ax.set_xlabel('Frame id')
    ax.set_ylabel('Frame loss rate')
    ax.set_ylim(0, 1)

    ax = axes[1]
    avg_ssim = df['ssim'].mean()
    ax.plot(df['frame_id'], df['ssim'], color='C1',
            label=f'avg = {avg_ssim:.3f}')
    ax.set_xlabel('Frame id')
    ax.set_ylabel('SSIM')
    ax.legend()

    ax = axes[2]
    frame_delay_ms = df['frame_decode_ts_ms'] - df['frame_encode_ts_ms']
    avg_frame_delay_ms = frame_delay_ms.mean()
    ax.plot(df['frame_id'], frame_delay_ms,
            color='C2', label=f'avg = {avg_frame_delay_ms:.2f}')
    ax.set_xlabel('Frame id')
    ax.set_ylabel('Frame delay(ms)')
    ax.legend()

    fig.tight_layout()
    if save_dir:
        fig.savefig(os.path.join(save_dir, '{}_codec_log_plot.jpg'.format(cc)),
                    bbox_inches='tight')
    plt.close()
