import glob
import os
import re
import subprocess

import matplotlib.pyplot as plt
import pandas as pd

DATALINK_CMD = "tshark -2 -r {} -Y tcp.dstport==5001 -T fields -e frame.time_relative \
        -e tcp.seq -e tcp.analysis.rto -e tcp.analysis.retransmission -e tcp.analysis.fast_retransmission -E header=y -E separator=,"
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
                outputs.append(output)
    return pd.DataFrame(outputs)

def main():
    trace_dir = "results/pcap_traces/blackbox-aws-test-ss"
    tcp_traces = glob.glob(os.path.join(trace_dir, "tcp_*.pcap"))
    for tcp_trace in tcp_traces:
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

        fig, axes = plt.subplots(5, 1, figsize=(14, 12))

        ax = axes[0]
        ax.plot(df_al['frame.time_relative'], df_al['tcp.analysis.ack_rtt'] * 1000, 'o-', ms=2, label='RTT')
        try:
            ax.set_xlim(0, t_max)
        except:
            continue
        ax.set_ylim(0, )
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('RTT (ms)')

        mask = (df_dl['tcp.analysis.fast_retransmission'] == 1) | (df_dl['tcp.analysis.retransmission'] == 1)
        ax.vlines(df_dl[mask]['frame.time_relative'], ymin=0, ymax=df_al['tcp.analysis.ack_rtt'].max() * 1000, ls='--', color='C1', label="(Fast) Rtx")
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

        ax = axes[4]
        if os.path.exists(ss_log):
            ax.plot(df_ss.index * 0.5, df_ss['cwnd'], 'o-', label='cwnd')
            ax.plot(df_ss.index * 0.5, df_ss['ssthresh'], 'o-', label='ssthresh')
            ax.set_xlim(0, )
            ax.set_ylim(0, )
            ax.legend()
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('# of packets')

        fig.tight_layout()
        fig.savefig(os.path.join(trace_dir, f"{trace_name}.jpg"), bbox_inches='tight')

        # plt.show()

if __name__ == '__main__':
    main()
