import glob
import os

import matplotlib.pyplot as plt
import pandas as pd
import subprocess

DATALINK_CMD = "tshark -2 -r {} -Y tcp.dstport==5001 -T fields -e frame.time_relative \
        -e tcp.seq -e tcp.analysis.rto -e tcp.analysis.retransmission -e tcp.analysis.fast_retransmission -E header=y -E separator=,"
ACKLINK_CMD = "tshark -2 -r {} -Y tcp.srcport==5001 -T fields -e frame.time_relative \
        -e tcp.ack -e tcp.analysis.ack_rtt -e tcp.analysis.duplicate_ack_num -E header=y -E separator=,"

def main():
    tcp_traces = glob.glob("results/pcap_traces/blackbox-aws-cell/tcp_*.pcap")
    for tcp_trace in tcp_traces:
        data_cmd = DATALINK_CMD.format(tcp_trace)
        ack_cmd = ACKLINK_CMD.format(tcp_trace)
        trace_name = os.path.basename(tcp_trace).split('.')[0]

        datalink_log = "datalink.csv"
        acklink_log = "acklink.csv"
        with open(datalink_log, 'w') as f:
            subprocess.run(data_cmd.split(), stdout=f)
        with open(acklink_log, 'w') as f:
            subprocess.run(ack_cmd.split(), stdout=f)

        df_dl = pd.read_csv(datalink_log)
        df_al = pd.read_csv(acklink_log)
        t_max = max(df_dl['frame.time_relative'].max(), df_al['frame.time_relative'].max()) + 1

        fig, axes = plt.subplots(2, 1, figsize=(14, 8))

        ax = axes[0]
        ax.plot(df_al['frame.time_relative'], df_al['tcp.analysis.ack_rtt'] * 1000, 'o-', ms=2, label='RTT')
        try:
            ax.set_xlim(0, t_max)
        except:
            continue
        ax.set_ylim(0, 1000)
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
        # fig.legend()

        # ax.plot(df_dl['frame.time_relative'], df_dl['tcp.analysis.retransmission'], '.')
        # ax.set_xlim(0, )
        # ax.set_xlabel('Time (s)')
        # # ax.set_ylabel('Ack no.')

        fig.tight_layout()
        fig.savefig(f"results/pcap_traces/blackbox-aws-cell/{trace_name}.jpg", bbox_inches='tight')

        # plt.show()


if __name__ == '__main__':
    main()
