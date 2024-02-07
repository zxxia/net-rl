import glob
import os
import re
import subprocess

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

SRTT_ALPHA = 1 / 8

DATALINK_CMD = "tshark -2 -r {} -Y tcp.dstport==5001 -T fields -e frame.number -e frame.time_relative \
        -e tcp.seq -e tcp.analysis.rto -e tcp.analysis.rto_frame -e tcp.analysis.retransmission -e tcp.analysis.fast_retransmission -E header=y -E separator=,"
ACKLINK_CMD = "tshark -2 -r {} -Y tcp.srcport==5001 -T fields -e frame.time_relative \
        -e tcp.ack -e tcp.analysis.ack_rtt -e tcp.analysis.duplicate_ack_num -E header=y -E separator=,"
TPUT_CMD = "tshark -r {} -q -z io,stat,0.5,tcp.dstport==5001 | grep -P '\d+\.?\d*\s+<>\s+|Interval +\|' | tr -d ' ' | tr '|' ',' | sed -E 's/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g' > {}"

def parse_ss_output(log_name):
    outputs = []
    with open(log_name, 'r') as f:
        for line in f:
            output = {}
            line = line.rstrip()
            if line.startswith("\t"):
                cols = re.sub(r"[\n\t]*", '', line).split()
                for col in cols:
                    if col.startswith('cwnd') or col.startswith('ssthresh'):
                        key, val = col.split(':')
                        output[key] = int(val)
                    elif col.startswith('rtt'):
                        key, val = col.split(':')
                        srtt, rttvar = val.split('/')
                        output[key] = float(srtt)
                        output['rttvar'] = float(rttvar)
                outputs.append(output)
    return pd.DataFrame(outputs)

def main():
    trace_dir = "results/pcap_traces/blackbox-aws-test-campus"
    tcp_traces = glob.glob(os.path.join(trace_dir, "tcp_*.pcap"))
    for trace_idx, tcp_trace in enumerate(tcp_traces):
        data_cmd = DATALINK_CMD.format(tcp_trace)
        ack_cmd = ACKLINK_CMD.format(tcp_trace)
        trace_name = os.path.basename(tcp_trace).split('.')[0]
        trace_ts = trace_name.split('_')[1]

        datalink_log = os.path.join(trace_dir, f"{trace_name}_datalink.csv")
        acklink_log = os.path.join(trace_dir, f"{trace_name}_acklink.csv")
        tput_log = os.path.join(trace_dir, f"{trace_name}_tput.csv")
        ss_log = os.path.join(trace_dir, f"ss_output_{trace_ts}.log")
        if not os.path.exists(datalink_log):
            with open(datalink_log, 'w') as f:
                subprocess.run(data_cmd.split(), stdout=f)
        if not os.path.exists(acklink_log):
            with open(acklink_log, 'w') as f:
                subprocess.run(ack_cmd.split(), stdout=f)

        if not os.path.exists(tput_log):
            cmd = TPUT_CMD.format(tcp_trace, tput_log)
            os.system(cmd)

        if os.path.exists(ss_log):
            df_ss = parse_ss_output(ss_log)

        df_dl = pd.read_csv(datalink_log)
        df_al = pd.read_csv(acklink_log)
        df_tput = pd.read_csv(tput_log)
        t_max = max(df_dl['frame.time_relative'].max(), df_al['frame.time_relative'].max()) + 1
        my_srtt = []
        for rtt in df_al['tcp.analysis.ack_rtt'].to_numpy():
            if not my_srtt:
                my_srtt.append(rtt * 1000)
            elif np.isnan(my_srtt[-1]) and not np.isnan(rtt):
                my_srtt.append(rtt * 1000)
            elif not np.isnan(my_srtt[-1]) and np.isnan(rtt):
                my_srtt.append(my_srtt[-1])
            else:
                my_srtt.append((1 - SRTT_ALPHA) * my_srtt[-1] + SRTT_ALPHA * rtt * 1000)
        df_al.insert(1, 'srtt', my_srtt, True)

        fig, axes = plt.subplots(6, 1, figsize=(14, 16))

        ax = axes[0]
        rtt_mean = round(df_al['tcp.analysis.ack_rtt'].mean() * 1000)
        rtt_min = round(df_al['tcp.analysis.ack_rtt'].min() * 1000)
        rtt_max = round(df_al['tcp.analysis.ack_rtt'].max() * 1000)
        rtt_median = round(df_al['tcp.analysis.ack_rtt'].median() * 1000)
        ax.plot(df_al['frame.time_relative'],
                df_al['tcp.analysis.ack_rtt'] * 1000, 'o-', ms=2,
                label=f'RTT min {rtt_min}, max {rtt_max}, mean {rtt_mean}, 50P {rtt_median}')
        try:
            ax.set_xlim(0, t_max)
        except:
            continue
        ax.set_ylim(0, )
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('RTT (ms)')


        mask0 = df_dl['tcp.analysis.fast_retransmission'] == 1
        mask1 = df_dl['tcp.analysis.retransmission'] == 1

        mask = mask0 | mask1
        fast_rtx_ts = df_dl[mask0]['frame.time_relative']
        timeout_rtx_ts = df_dl[mask1]['frame.time_relative']
        rtx_ts = df_dl[mask]['frame.time_relative']
        # rtx_frame_num = df_dl[mask]['frame.number']
        # rtx_rto_frame = df_dl[mask]['tcp.analysis.rto_frame']
        rtx_seq = df_dl[mask]['tcp.seq']

        ax.vlines(rtx_ts, ymin=0, ymax=df_al['tcp.analysis.ack_rtt'].max() * 1000, ls='--', color='C1', label="(Fast) Rtx")
        # ax.vlines(fast_rtx_ts, ymin=0, ymax=df_al['tcp.analysis.ack_rtt'].max() * 1000, ls='--', color='C1', label="Fast Rtx")
        # ax.vlines(timeout_rtx_ts, ymin=0, ymax=df_al['tcp.analysis.ack_rtt'].max() * 1000, ls='--', color='C2', label="Rtx")
        ax.legend()

        ax = axes[1]
        ax.plot(df_al['frame.time_relative'], df_al['tcp.analysis.duplicate_ack_num'], 'o', ms=2, label='Dup ack num')
        # ax.vlines(df_dl[mask]['frame.time_relative'], ymin=0, ymax=df_al['tcp.analysis.ack_rtt'].max() * 1000, ls='--', color='C1', label="(Fast) Rtx")

        ax.set_xlim(0, t_max)
        ax.set_ylim(0, )
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Dup ack num')
        ax_twinx = ax.twinx()
        ax_twinx.plot(df_dl['frame.time_relative'], df_dl['tcp.analysis.rto'], 'o', color='C2', ms=2, label='RTO')
        ax_twinx.set_ylabel('Segment RTO (s)')
        ax_twinx.set_ylim(0, )

        ax = axes[2]
        ax.plot(df_dl['frame.time_relative'], df_dl['tcp.seq'], 'o', ms=2)
        ax.set_xlim(0, t_max)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Seq #')

        ax = axes[3]
        dur_sec = df_tput['Stop'].iloc[0] - df_tput['Start'].iloc[0]
        ax.plot(df_tput['Start'], df_tput['Bytes'] / dur_sec, 'o-', ms=2, label='Send Rate')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Rate (byte/s)')
        ax.legend()
        ax.set_xlim(0, t_max)
        ax.set_ylim(0, )

        if os.path.exists(ss_log):
            ax = axes[4]
            ax.plot(df_ss.index * 0.5, df_ss['cwnd'], 'o-', label='cwnd')
            ax.plot(df_ss.index * 0.5, df_ss['ssthresh'], 'o-', label='ssthresh')
            ax.set_xlim(0, t_max)
            ax.set_ylim(0, )
            ax.legend()
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('# of packets')

            ax = axes[5]
            ax.plot(df_ss.index * 0.5, df_ss['rtt'], 'o-', label='srtt')
            ax.set_xlim(0, t_max)
            ax.set_ylim(0, )
            ax.legend()
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('srtt (ms)')
        fig.tight_layout()
        fig.savefig(os.path.join(trace_dir, f"{trace_name}.jpg"), bbox_inches='tight')


        plt.figure()
        ax = plt.gca()
        # ax = axes[6]
        # ax.plot(df_al['frame.time_relative'], df_al['srtt'], 'o-', label='my srtt')
        # ax.plot(df_al['frame.time_relative'][1:], np.diff(my_srtt), 'o-', label='my srtt')
        # grad = np.diff(my_srtt) / np.diff(df_al['frame.time_relative'])
        # ax.plot(df_al['frame.time_relative'][1:], grad, 'o-', label='grad')
        # peak_idx, properties = find_peaks(df_al['srtt'], height=50)

        # ax.plot(df_al['frame.time_relative'].to_numpy()[peak_idx], df_al['srtt'].to_numpy()[peak_idx], 'x', label='peak')
        num_above_thresh = 0
        # for t in rtx_ts:
        #     mask = (df_al['frame.time_relative'] >= t - 4 * rtt_min / 1000) & (df_al['frame.time_relative'] < t)
        #     # mask = (df_al['frame.time_relative'] >= t - 0.12) & (df_al['frame.time_relative'] < t)
        #     ax.plot(df_al[mask]['frame.time_relative'], df_al[mask]['tcp.analysis.ack_rtt'] * 1000, 'o-', color='C0')
        #     # print(df_al[mask]['frame.time_relative'].iloc[-10:], df_al[mask]['srtt'].iloc[-10:])
        #     # print(len(df_al[mask]['srtt']))
        #     if (df_al[mask]['tcp.analysis.ack_rtt'].max() - df_al[mask]['tcp.analysis.ack_rtt'].min()) * 1000 > 50:
        #         num_above_thresh += 1

        for seq, t_end in zip(rtx_seq, rtx_ts):
            try:
                t_start = df_dl[df_dl['tcp.seq'] == seq].iloc[0]['frame.time_relative'].item()
            except:
                import pdb; pdb.set_trace()
            mask = (df_al['frame.time_relative'] >= t_start) & (df_al['frame.time_relative'] < t_end)
            ax.plot(df_al[mask]['frame.time_relative'], df_al[mask]['tcp.analysis.ack_rtt'] * 1000, 'o-', color='C0')
            if (df_al[mask]['tcp.analysis.ack_rtt'].max() - df_al[mask]['tcp.analysis.ack_rtt'].min()) * 1000 > 30:
                num_above_thresh += 1
            # mask = (df_al['frame.time_relative'] >= t - 4 * rtt_min / 1000) & (df_al['frame.time_relative'] < t)
            # print(start, end)
            # import pdb; pdb.set_trace()

        print(f"trace {trace_idx}: RTT increase above 30ms: {num_above_thresh}, total: {len(rtx_ts)}, percent above thresh {num_above_thresh / len(rtx_ts):.2f}") #, percent below thresh {1 - num_above_thresh / len(rtx_ts):.2f}")


        ax.vlines(rtx_ts, ymin=0, ymax=200, ls='--', color='C1', label="(Fast) Rtx")
        ax.set_xlim(0, t_max)
        ax.set_ylim(0, )
        ax.legend()
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('my srtt (ms)')
        # np.gradient(df_al['tcp.analysis.ack_rtt'] * 1000, df_al['frame.time_relative']))

        # plt.show()

if __name__ == '__main__':
    main()
