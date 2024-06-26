import csv
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MODEL_ID_MAP = {64: 1, 128: 2, 256: 3, 512: 4, 1024: 5, 2048: 6, 4096: 7,
                6144: 8, 8192: 9, 12288: 10, 16384: 11}

class PktLog():
    def __init__(self, pkt_sent_ts_us: List[int],
                 pkt_rcvd_ts_us: List[int],
                 first_ts_us, binwise_bytes_sent: Dict[int, int],
                 binwise_bytes_rcvd: Dict[int, int],
                 owds_ms: List[int],
                 packet_log_file: Optional[str] = None,
                 bin_size_ms: int = 500):
        self.pkt_log_file = packet_log_file
        self.pkt_sent_ts_us = pkt_sent_ts_us
        self.pkt_rcvd_ts_us = pkt_rcvd_ts_us
        self.bin_size_ms = bin_size_ms
        self.first_ts_us = first_ts_us

        self.binwise_bytes_sent = binwise_bytes_sent
        self.binwise_bytes_rcvd = binwise_bytes_rcvd
        self.owds_ms = owds_ms

        self.avg_sending_rate_mbps = None
        self.avg_tput_mbps = None
        self.avg_ack_rate_mbps = None
        self.avg_rtt_ms = None

    @classmethod
    def from_log_file(cls, packet_log_file: str, bin_size_ms: int = 500):
        pkt_sent_ts_us = []
        pkt_rcvd_ts_us = []

        first_ts_us = None

        binwise_bytes_sent = {}
        binwise_bytes_rcvd = {}
        owds_ms = []
        with open(packet_log_file, 'r') as f:
            reader = csv.reader(f)
            for line in reader:
                # skip header
                if line[0] == 'timestamp_us':
                    continue
                ts_us = int(line[0])
                direction = line[1]
                seq_num = int(line[2])
                pkt_byte = int(line[3])
                owd_ms = int(line[4]) if line[4] else 0
                if first_ts_us is None:
                    first_ts_us = ts_us
                if direction == "-":
                    pkt_sent_ts_us.append(ts_us)
                    bin_id = cls.ts_to_bin_id(ts_us, first_ts_us, bin_size_ms * 1e3)
                    binwise_bytes_sent[bin_id] = binwise_bytes_sent.get(
                        bin_id, 0) + pkt_byte
                elif direction == '+':
                    pkt_rcvd_ts_us.append(ts_us)
                    bin_id = cls.ts_to_bin_id(ts_us, first_ts_us, bin_size_ms * 1e3)
                    binwise_bytes_rcvd[bin_id] = binwise_bytes_rcvd.get(
                        bin_id, 0) + pkt_byte
                    owds_ms.append(owd_ms)
                else:
                    raise RuntimeError(
                        "Unrecognized direction {}!".format(direction))
        return cls(pkt_sent_ts_us, pkt_rcvd_ts_us, first_ts_us,
                   binwise_bytes_sent, binwise_bytes_rcvd, owds_ms,
                   packet_log_file=packet_log_file, bin_size_ms=bin_size_ms)

    @staticmethod
    def ts_to_bin_id(ts, first_ts, bin_size) -> int:
        return int((ts - first_ts) / bin_size)

    @staticmethod
    def bin_id_to_s(bin_id, bin_size) -> float:
        return (bin_id * bin_size) / 1e3

    # def get_ack_rate_mbps(self) -> Tuple[List[float], List[float]]:
    #     ts_sec = []
    #     ack_rate_mbps = []
    #     for bin_id in sorted(self.binwise_bytes_acked):
    #         ts_sec.append(self.bin_id_to_s(bin_id, self.bin_size_ms))
    #         ack_rate_mbps.append(
    #             self.binwise_bytes_acked[bin_id] * 8 / self.bin_size_ms / 1e3)
    #     return ts_sec, ack_rate_mbps

    def get_throughput_mbps(self) -> Tuple[List[float], List[float]]:
        ts_sec = []
        tput_mbps = []
        for bin_id in sorted(self.binwise_bytes_rcvd):
            ts_sec.append(self.bin_id_to_s(bin_id, self.bin_size_ms))
            tput_mbps.append(
                self.binwise_bytes_rcvd[bin_id] * 8 / self.bin_size_ms / 1e3)
        return ts_sec, tput_mbps

    def get_sending_rate_mbps(self) -> Tuple[List[float], List[float]]:
        ts_sec = []
        sending_rate_mbps = []
        for bin_id in sorted(self.binwise_bytes_sent):
            ts_sec.append(self.bin_id_to_s(bin_id, self.bin_size_ms))
            sending_rate_mbps.append(
                self.binwise_bytes_sent[bin_id] * 8 / self.bin_size_ms / 1e3)
        return ts_sec, sending_rate_mbps

    # def get_rtt_ms(self) -> Tuple[List[float], List[int]]:
    #     return [ts_ms / 1e3 for ts_ms in self.pkt_acked_ts_ms], self.pkt_rtt_ms
    #
    def get_owd_ms(self) -> Tuple[List[float], List[int]]:
        return [ts_us / 1e6 for ts_us in self.pkt_rcvd_ts_us], self.owds_ms

    def get_loss_rate(self) -> float:
        if self.pkt_rcvd_ts_us:
            return 1 - len(self.pkt_rcvd_ts_us) / len(self.pkt_sent_ts_us)
        return 1 - len(self.pkt_rcvd_ts_us) / len(self.pkt_sent_ts_us)

    # # def get_reward(self, trace_file: str, trace=None) -> float:
    # #     if trace_file and trace_file.endswith('.json'):
    # #         trace = Trace.load_from_file(trace_file)
    # #     elif trace_file and trace_file.endswith('.log'):
    # #         trace = Trace.load_from_pantheon_file(trace_file, 0, 50, 500)
    # #     loss = self.get_loss_rate()
    # #     if trace is None:
    # #         # original reward
    # #         return pcc_aurora_reward(
    # #             self.get_avg_throughput() * 1e6 / 8 / BYTES_PER_PACKET,
    # #             self.get_avg_latency() / 1e3, loss)
    # #     # normalized reward
    # #     return pcc_aurora_reward(
    # #         self.get_avg_throughput() * 1e6 / 8 / BYTES_PER_PACKET,
    # #         self.get_avg_latency() / 1e3, loss,
    # #         trace.avg_bw * 1e6 / 8 / BYTES_PER_PACKET,
    # #         trace.min_delay * 2 / 1e3)
    #
    # def get_avg_sending_rate_mbps(self) -> float:
    #     if not self.pkt_sent_ts_ms:
    #         return 0.0
    #     if self.avg_sending_rate_mbps is None:
    #         dur_ms = self.pkt_sent_ts_ms[-1] - self.pkt_sent_ts_ms[0]
    #         bytes_sum = 0
    #         for _, bytes_sent in self.binwise_bytes_sent.items():
    #             bytes_sum += bytes_sent
    #         self.avg_sending_rate_mbps = bytes_sum * 8 / 1e3 / dur_ms
    #     return self.avg_sending_rate_mbps
    #
    # def get_avg_throughput_mbps(self) -> float:
    #     if not self.pkt_arrived_ts_ms:
    #         return 0.0
    #     if self.avg_tput_mbps is None:
    #         dur_ms = self.pkt_arrived_ts_ms[-1] - self.pkt_arrived_ts_ms[0]
    #         bytes_sum = 0
    #         for _, bytes_arrived in self.binwise_bytes_arrived.items():
    #             bytes_sum += bytes_arrived
    #         self.avg_tput_mbps = bytes_sum * 8 / 1e3 / dur_ms
    #     return self.avg_tput_mbps
    #
    # def get_avg_ack_rate_mbps(self) -> float:
    #     if not self.pkt_acked_ts_ms:
    #         return 0.0
    #     if self.avg_ack_rate_mbps is None:
    #         dur_ms = self.pkt_acked_ts_ms[-1] - self.pkt_acked_ts_ms[0]
    #         bytes_sum = 0
    #         for _, bytes_acked in self.binwise_bytes_acked.items():
    #             bytes_sum += bytes_acked
    #         self.avg_ack_rate_mbps = bytes_sum * 8 / 1e3 / dur_ms
    #     return self.avg_ack_rate_mbps
    #
    # def get_avg_rtt_ms(self) -> float:
    #     if self.avg_rtt_ms is None:
    #         self.avg_rtt_ms = np.mean(self.pkt_rtt_ms)
    #     return self.avg_rtt_ms
    #
    # def get_avg_owd_ms(self) -> Tuple[List[float], List[int]]:
    #     return np.mean(self.one_way_delays_ms)
    #
    # def get_owd_percentile_ms(self, p) -> float:
    #     return np.percentile(self.one_way_delays_ms, p)

pkt_log0 = PktLog.from_log_file("./pkt_log0.csv")
pkt_log1 = PktLog.from_log_file("./pkt_log1.csv")
# df = pd.read_csv('../../trace.csv')
df = pd.read_csv('./video_sender_log.csv')
df_vid_rcv = pd.read_csv('./video_receiver_log.csv')
df_fbra = pd.read_csv('./fbra_log.csv')

send_ts_sec, send_rate = pkt_log0.get_sending_rate_mbps()
tput_ts_sec, tput = pkt_log1.get_throughput_mbps()
owd_ts_sec, owd = pkt_log1.get_owd_ms()

fig, axes = plt.subplots(8, 1, figsize=(15, 10))
# print(tput)
ax = axes[0]
ax.plot(df['timestamp_us']/1e6, df['pacing_rate_bps']/1e6, label='pacing rate')
ax.plot(send_ts_sec, send_rate, 'o-', ms=2, label='send rate')
ax.plot(tput_ts_sec, tput, 'o-', ms=2, label='tput')
# plt.plot(df['timestamp_ms']/1000, df['bandwidth_mbps'], label='trace')
ax.plot(df['timestamp_us']/1e6, df['frame_bitrate_bps']/1e6, label='frame bitrate')
ax.plot(df['timestamp_us']/1e6, df['fec_data_rate_bps']/1e6, label='fec data rate')
ax.set_ylabel('Rate(Mbps)')
# ax.set_xlabel('Time (s)')
ax.set_ylim(0, )
ax.set_xlim(0, )
ax.legend()

ax = axes[1]
ax.plot(owd_ts_sec, owd, label='owd')
ax.plot(df_fbra['timestamp_us']/1e6, df_fbra['p40_owd_ms'], label='P40 owd')
ax.plot(df_fbra['timestamp_us']/1e6, df_fbra['p80_owd_ms'], label='P80 owd')
ax.set_ylabel('Delay(ms)')
# ax.set_xlabel('Time (s)')
ax.set_ylim(0, )
ax.set_xlim(0, )
ax.legend()

ax = axes[2]
frame_delay = df_vid_rcv['frame_decode_ts_us'] - df_vid_rcv["frame_encode_ts_us"]
ax.plot(df_vid_rcv['frame_decode_ts_us'] / 1e6, frame_delay / 1e3)
ax.set_xlim(0, )
ax.set_ylim(0, )
ax.set_ylabel('Frame delay (ms)')

ax = axes[3]
ax.plot(df_vid_rcv['frame_decode_ts_us'] / 1e6, df_vid_rcv['frame_loss_rate'])
ax.set_xlim(0, )
ax.set_ylim(0, 1)
ax.set_ylabel('Frame loss rate')

ax = axes[4]
ax.plot(df_vid_rcv['frame_decode_ts_us'] / 1e6, df_vid_rcv['ssim'])
ax.set_xlim(0, )
# ax.set_ylim(0, 1)
ax.set_ylabel('SSIM')

ax = axes[5]

model_ids = [MODEL_ID_MAP[val] for val in df_vid_rcv["model_id"]]
yticks = list(range(1, len(MODEL_ID_MAP)+1))
yticklabels = [str(k) for k in sorted(MODEL_ID_MAP)]
ax.plot(df_vid_rcv['frame_encode_ts_us'] / 1e6, model_ids)
ax.set_xlim(0, )
# ax.set_ylim(0, 1)
ax.set_ylabel('AE model id')
ax.set_yticks(yticks)
ax.set_yticklabels(yticklabels)

ax = axes[6]
ax.plot(df_fbra['timestamp_us']/1e6, df_fbra['state'], 'o-', ms=3, label='FBRA state')
ax.set_yticks([0, 1, 2, 3])
ax.set_yticklabels(['Down', 'Stay', "Up", 'Probe'])
# ax.set_xlabel('Time (s)')
ax.set_ylim(0, )
ax.set_xlim(0, )
ax.legend()

ax = axes[7]
ax.plot(df_fbra['timestamp_us']/1e6, df_fbra['corr_owd_low'], 'o-', ms=3, label='corr_owd_low')
ax.plot(df_fbra['timestamp_us']/1e6, df_fbra['corr_owd_high'], 'o-', ms=3, label='corr_owd_high')
ax.set_xlabel('Time (s)')
ax.set_ylabel('Correlated OWD')
ax.set_ylim(0, )
ax.set_xlim(0, )
ax.legend()

fig.set_tight_layout(True)
plt.show()
