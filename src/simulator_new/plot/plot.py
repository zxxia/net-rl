import os
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from simulator_new.constant import MODEL_ID_MAP
from simulator_new.stats_recorder import PacketLog
from simulator_new.trace import Trace


def ssim_to_db(ssim):
    return -10 * np.log10(1 - ssim)


def plot_mi_log(trace: Optional[Trace], log_file: str, save_dir: str, cc: str):
    df = pd.read_csv(log_file)
    assert isinstance(df, pd.DataFrame)
    ts_sec = df['timestamp_ms'] / 1e3
    recv_rate_mbps = df['recv_rate_Bps'] * 8 / 1e6
    avg_recv_rate_mbps = recv_rate_mbps.mean()
    send_rate_mbps = df['send_rate_Bps'] * 8 / 1e6
    send_recv_rate_mbps = send_rate_mbps.mean()
    avg_lat_ms = df['latency_ms'].mean()
    avg_loss_ratio = df['loss_ratio'].mean()
    fig, axes = plt.subplots(9, 1, figsize=(12, 15))
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

    axes[3].plot(ts_sec, df['reward'],
                 label='rewards avg {:.3f}'.format(df['reward'].mean()))
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

    ax = axes[6]
    if 'sent_latency_inflation' in df:
        ax.plot(ts_sec, df['sent_latency_inflation'])
        ax.set_ylabel('Sent latency inflation')
        ax.set_xlabel("Time(s)")
        ax.set_xlim(0, ts_max)

    ax = axes[7]
    if 'latency_ratio' in df:
        ax.plot(ts_sec, df['latency_ratio'])
        ax.set_ylabel('Latency ratio')
        ax.set_xlabel("Time(s)")
        ax.set_xlim(0, ts_max)

    ax = axes[8]
    if 'recv_ratio' in df:
        ax.plot(ts_sec, df['recv_ratio'])
        ax.set_ylabel('Recv ratio')
        ax.set_xlabel("Time(s)")
        ax.set_xlim(0, ts_max)

    plt.tight_layout()
    if save_dir is not None:
        fig.savefig(os.path.join(save_dir, "{}_time_series.jpg".format(cc)),
                    bbox_inches='tight')
    plt.close()


def plot_pkt_log(trace, log_file, save_dir, cc, decoder_log: Optional[str] = None):
    pkt_log = PacketLog.from_log_file(log_file, 500)
    sending_rate_ts_sec, sending_rate_mbps = pkt_log.get_sending_rate_mbps()
    tput_ts_sec, tput_mbps = pkt_log.get_throughput_mbps()
    rtt_ts_sec, rtt_ms = pkt_log.get_rtt_ms()
    owd_ts_sec, owd_ms = pkt_log.get_owd_ms()
    pkt_loss_rate = pkt_log.get_loss_rate()
    avg_tput_mbps = pkt_log.get_avg_throughput_mbps()
    avg_sending_rate_mbps = pkt_log.get_avg_sending_rate_mbps()
    avg_lat = pkt_log.get_avg_rtt_ms()
    # reward = pkt_log.get_reward("", None)
    # normalized_reward = pkt_log.get_reward("", trace)
    ts_max = min([trace.timestamps[-1], sending_rate_ts_sec[-1], tput_ts_sec[-1]])

    if decoder_log:
        fig, axes = plt.subplots(7, 1, figsize=(15, 13))
        plot_decoder_log(decoder_log, save_dir, cc, np.concatenate([axes[:1], axes[2:]]), ts_max)
    else:
        fig, axes = plt.subplots(2, 1, figsize=(6, 8))
    axes[0].plot(tput_ts_sec, tput_mbps, "-o", ms=2,  # drawstyle='steps-post',
                 label='tput, avg {:.3f}Mbps'.format(avg_tput_mbps))
    axes[0].plot(sending_rate_ts_sec, sending_rate_mbps, "-o", ms=2,  # drawstyle='steps-post',
                 label='send rate, avg {:.3f}Mbps'.format(avg_sending_rate_mbps))
    if trace is not None:
        axes[0].plot(trace.timestamps, trace.bandwidths, "-o", ms=2,  # drawstyle='steps-post',
                     label='bw, avg {:.3f}Mbps'.format(np.mean(trace.bandwidths)))
        queue_size = trace.queue_size
        trace_random_loss = trace.loss_rate
        delay_noise = trace.delay_noise
    else:
        queue_size = "N/A"
        trace_random_loss = "N/A"
        delay_noise = "N/A"
        # axes[0].plot(np.arange(30), np.ones_like(np.arange(30)) * 6, "-o", ms=2,  # drawstyle='steps-post',
        #              label='bandwidth, avg {:.3f}Mbps'.format(6))
    axes[0].legend()
    # axes[0].set_xlabel("(Decode) Time(s)")
    axes[0].set_xlabel("(encode) Time(s)")
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
    axes[1].plot(owd_ts_sec, owd_ms, ms=2, label='OWD, avg {:.3f}ms'.format(np.mean(owd_ms)))
    if trace is not None:
        xvals = np.arange(0, ts_max + 1)
        axes[1].plot(xvals, np.ones_like(xvals) * 2 * trace.min_delay, c='C2',
                     label="min prop delay {:.3f}ms".format(2*trace.min_delay))
    axes[1].legend()
    axes[1].set_xlabel("Time(s)")
    axes[1].set_ylabel("Latency(ms)")
    axes[1].set_title('{} loss={:.3f}, rand loss={:.3f}, queue cap={}pkt'.format(
        cc, pkt_loss_rate, trace_random_loss, int(queue_size)))
    axes[1].set_xlim(0, ts_max)

    fig.tight_layout()
    if save_dir:
        fig.savefig(os.path.join(save_dir, '{}_pkt_log_plot.jpg'.format(cc)),
                    bbox_inches='tight')
    plt.close()


def plot_decoder_log(decoder_log, save_dir, cc, axes=[], ts_max=0.0):
    fig = None
    df = pd.read_csv(decoder_log)
    if len(axes) == 0:
        fig, axes = plt.subplots(6, 1, figsize=(15, 13))
    frame_enc_ts_sec = df['frame_encode_ts_ms'] / 1000
    frame_dec_ts_sec = df['frame_decode_ts_ms'] / 1000
    ax = axes[0]
    ax.plot(frame_enc_ts_sec, df['target_bitrate_Bps'] * 8e-6, 'o-', ms=2,
            color='C3', label='target bitrate')

    ax = axes[1]
    ax.plot(frame_dec_ts_sec, df['frame_loss_rate'], 'o-', ms=2, color='C0')
    ax.set_xlabel('(Decode) Time(s)')
    ax.set_ylabel('Frame loss rate')
    ax.set_xlim(0, ts_max)
    ax.set_ylim(0, 1)
    ax2 = ax.twiny()
    ax2.set_xlabel('Frame id')
    nticks = len(ax.get_xticks())
    step_len = int((len(df['frame_id']) - 1) / (nticks - 1))
    ax2_xticks = [frame_dec_ts_sec.iloc[i * step_len] for i in range(nticks)]
    ax2_xticklabels = [str(df['frame_id'].iloc[i * step_len]) for i in range(nticks)]
    ax2.set_xbound(ax.get_xbound())
    ax2.set_xticks(ax2_xticks)
    ax2.set_xticklabels(ax2_xticklabels)
    ax2.set_xlim(0, ts_max)

    ax = axes[2]
    ssim_db = ssim_to_db(df['ssim'].to_numpy())
    avg_ssim = np.mean(ssim_db)
    p5_ssim = np.percentile(ssim_db, 5)
    p50_ssim = np.median(ssim_db)
    ax.plot(frame_dec_ts_sec, ssim_db, 'o-', ms=2, color='C1',
            label=f'avg={avg_ssim:.3f}dB, P5={p5_ssim:.3f}dB, P50={p50_ssim:.3f}dB')
    ax.set_xlabel('(Decode) Time(s)')
    ax.set_ylabel('SSIM (dB)')
    ax.set_xlim(0, ts_max)
    ax.legend()
    ax2 = ax.twiny()
    ax2.set_xlabel('Frame id')
    ax2.set_xbound(ax.get_xbound())
    ax2.set_xticks(ax2_xticks)
    ax2.set_xticklabels(ax2_xticklabels)
    ax2.set_xlim(0, ts_max)

    ax = axes[3]
    frame_delay_ms = df['frame_decode_ts_ms'] - df['frame_encode_ts_ms']
    avg_frame_delay_ms = frame_delay_ms.mean()
    p95_frame_delay_ms = np.percentile(frame_delay_ms, 95)
    ax.plot(frame_dec_ts_sec, frame_delay_ms, 'o-', ms=2,
            color='C2', label=f'avg={avg_frame_delay_ms:.2f}ms, P95={p95_frame_delay_ms:.2f}ms')
    ax.set_xlabel('(Decode) Time(s)')
    ax.set_xlim(0, ts_max)
    ax.set_ylabel('Frame delay(ms)')
    ax.legend()
    ax2 = ax.twiny()
    ax2.set_xlabel('Frame id')
    ax2.set_xbound(ax.get_xbound())
    ax2.set_xticks(ax2_xticks)
    ax2.set_xticklabels(ax2_xticklabels)
    ax2.set_xlim(0, ts_max)

    ax = axes[4]
    frame_decode_gap_ms = df['frame_decode_ts_ms'].diff()
    avg_gap_ms = frame_decode_gap_ms.mean()
    ax.plot(frame_dec_ts_sec, frame_decode_gap_ms, 'o-', ms=2,
            color='C3', label=f'avg = {avg_gap_ms:.2f}ms')
    ax.set_xlabel('(Decode) Time(s)')
    ax.set_xlim(0, ts_max)
    ax.set_ylabel('Frame decode\ngap(ms)')
    ax.legend()
    ax2 = ax.twiny()
    ax2.set_xlabel('Frame id')
    ax2.set_xbound(ax.get_xbound())
    ax2.set_xticks(ax2_xticks)
    ax2.set_xticklabels(ax2_xticklabels)
    ax2.set_xlim(0, ts_max)

    ax = axes[5]
    model_ids = [MODEL_ID_MAP[val] for val in df["model_id"]]
    yticks = list(range(1, len(MODEL_ID_MAP)+1))
    yticklabels = [str(k) for k in sorted(MODEL_ID_MAP)]
    ax.plot(frame_enc_ts_sec, model_ids, 'o-', c='C6', ms=2)
    ax.set_xlabel('(Encode) Time(s)')
    ax.set_xlim(0, ts_max)

    ax.set_ylim(1, len(MODEL_ID_MAP))
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels)
    ax.set_ylabel('AE model id')
    ax2 = ax.twiny()
    ax2.set_xlabel('Frame id')
    nticks = len(ax.get_xticks())
    step_len = int((len(df['frame_id']) - 1) / (nticks - 1))
    ax2_xticks = [frame_enc_ts_sec.iloc[i * step_len] for i in range(nticks)]
    ax2_xticklabels = [str(df['frame_id'].iloc[i * step_len]) for i in range(nticks)]
    ax2.set_xbound(ax.get_xbound())
    ax2.set_xticks(ax2_xticks)
    ax2.set_xticklabels(ax2_xticklabels)
    ax2.set_xlim(0, ts_max)

    if save_dir and fig:
        fig.tight_layout()
        fig.savefig(os.path.join(save_dir, '{}_codec_log_plot.jpg'.format(cc)),
                    bbox_inches='tight')

def plot_gcc_log(trace, src_gcc_log_path, dst_gcc_log_path, pacer_log_path, save_dir):
    df_src = pd.read_csv(src_gcc_log_path)
    df = pd.read_csv(dst_gcc_log_path)
    df_pacer = pd.read_csv(pacer_log_path)

    fig, axes = plt.subplots(5, 1, figsize=(12, 13))

    ax = axes[0]
    ax.plot(trace.timestamps, trace.bandwidths, "-o", ms=2,  # drawstyle='steps-post',
            label='bw, avg {:.3f}Mbps'.format(np.mean(trace.bandwidths)))
    ax.plot(df_src['timestamp_ms'] / 1000,
            df_src['loss_based_est_rate_Bps'] * 8e-6, label='Loss-based est')
    ax.plot(df_src['timestamp_ms'] / 1000,
            df_src['delay_based_est_rate_Bps'] * 8e-6, label='Delay-based est')
    ax.plot(df['timestamp_ms'] / 1000, df['rcv_rate_Bps'] * 8e-6, label='rcv rate')
    ax.plot(df_pacer['timestamp_ms'] / 1000, df_pacer['pacing_rate_Bps'] * 8e-6,
            '--', alpha=0.8, label='Pacing rate')
    ax.set_xlim(0, )
    ax.legend()
    ax.set_xlabel("Time(s)")
    ax.set_ylabel('Rate(Mbps)')

    ax = axes[1]
    ax.plot(df['timestamp_ms'] / 1000, df['delay_gradient'], 'o', ms=1, label='gradient')
    ax.plot(df['timestamp_ms'] / 1000, df['delay_gradient_hat'], 'o', ms=1, label='gradient_hat')
    ax.plot(df['timestamp_ms'] / 1000, df['gamma'], 'o', ms=1, label='gamma')
    ax.plot(df['timestamp_ms'] / 1000, -df['gamma'], 'o', ms=1, c='C2')
    ax.axhline(y=12.5, c='C3', label='static gamma')
    ax.axhline(y=-12.5, c='C3')
    ax.set_xlim(0, )
    ax.legend()
    ax.set_xlabel("Time(s)")
    ax.set_ylabel('Gradient(ms)')

    ax = axes[2]
    mask = df['remote_rate_controller_state'] == 'Increase'
    ax.plot(df[mask]['timestamp_ms'] / 1000, np.ones(len(df[mask])), 'o', label='Inc')
    mask = df['remote_rate_controller_state'] == 'Hold'
    ax.plot(df[mask]['timestamp_ms'] / 1000, np.zeros(len(df[mask])), 'o', label='Hold')
    mask = df['remote_rate_controller_state'] == 'Decrease'
    ax.plot(df[mask]['timestamp_ms'] / 1000, -1 * np.ones(len(df[mask])), 'o', label='Dec')
    ax.set_xlim(0, )
    ax.legend()
    ax.set_xlabel("Time(s)")
    ax.set_ylabel('Remote rate controller state')

    ax = axes[3]
    mask = df['overuse_signal'] == 'overuse'
    ax.plot(df[mask]['timestamp_ms'] / 1000, np.ones(len(df[mask])), 'o', label='overuse')
    mask = df['overuse_signal'] == 'normal'
    ax.plot(df[mask]['timestamp_ms'] / 1000, np.zeros(len(df[mask])), 'o', label='normal')
    mask = df['overuse_signal'] == 'underuse'
    ax.plot(df[mask]['timestamp_ms'] / 1000, -1 * np.ones(len(df[mask])), 'o', label='underuse')
    ax.set_xlim(0, )
    ax.set_ylim(-1.01, 1.01)
    ax.legend()
    ax.set_xlabel("Time(s)")
    ax.set_ylabel('Overuse signal')

    ax = axes[4]
    ax.plot(df_src['timestamp_ms'] / 1000, df_src['loss_fraction'], 'o', label='')
    ax.set_xlim(0, )
    ax.set_xlabel("Time(s)")
    ax.set_ylabel('Loss fraction')
    ax.set_ylim(0, 1)

    fig.tight_layout()
    fig.savefig(os.path.join(save_dir, 'gcc_log_plot.jpg'), bbox_inches='tight')
