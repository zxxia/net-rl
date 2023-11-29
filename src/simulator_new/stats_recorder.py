import csv
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from simulator_new.constant import BITS_PER_BYTE
from simulator_new.packet import Packet

class StatsRecorder:
    def __init__(self, log_dir) -> None:
        self.log_dir = log_dir
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
            self.log_fh = open(os.path.join(log_dir, "pkt_log.csv"), 'w', 1)
            self.csv_writer = csv.writer(self.log_fh, lineterminator="\n")
            self.csv_writer.writerow(
                ["timestamp_ms", "pkt_id", "pkt_type", "size_bytes", "rtt_ms"])
        else:
            self.log_fh = None
            self.csv_writer = None

        # tx host stats
        self.pkts_sent = 0
        self.bytes_sent = 0
        self.first_pkt_sent_ts_ms = -1
        self.pkt_sent_ts_ms = -1

        self.pkts_acked = 0
        self.bytes_acked = 0
        self.first_pkt_acked_ts_ms = -1
        self.pkt_acked_ts_ms = -1

        self.pkts_lost = 0
        self.bytes_lost = 0

        # rx host stats
        self.pkts_rcvd = 0
        self.bytes_rcvd = 0
        self.first_pkt_rcvd_ts_ms = -1
        self.pkt_rcvd_ts_ms = -1

    def __del__(self):
        if self.log_fh:
            self.log_fh.close()


    def on_pkt_sent(self, ts_ms, pkt):
        """called by tx host"""
        self.pkts_sent += 1
        self.bytes_sent += pkt.size_bytes
        if self.first_pkt_sent_ts_ms == -1:
            self.first_pkt_sent_ts_ms = ts_ms
        self.pkt_sent_ts_ms = ts_ms
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, pkt.pkt_id, pkt.pkt_type, pkt.size_bytes])

    def on_pkt_acked(self, ts_ms, pkt):
        """called by tx host"""
        self.pkts_acked += 1
        self.bytes_acked += pkt.size_bytes
        if self.first_pkt_acked_ts_ms == -1:
            self.first_pkt_acked_ts_ms = ts_ms
        self.pkt_acked_ts_ms = ts_ms
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, pkt.pkt_id, pkt.pkt_type, pkt.size_bytes,
                 pkt.delay_ms(), pkt.rtt_ms()])

    def on_pkt_lost(self, ts_ms, pkt):
        """called by tx host"""
        self.pkts_lost += 1
        self.bytes_lost += pkt.size_bytes
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, pkt.pkt_id, 'lost', pkt.size_bytes])

    def on_pkt_received(self, ts_ms, pkt):
        """called by rx host"""
        self.pkts_rcvd += 1
        self.bytes_rcvd += pkt.size_bytes
        if self.first_pkt_rcvd_ts_ms == -1:
            self.first_pkt_rcvd_ts_ms = ts_ms
        self.pkt_rcvd_ts_ms = ts_ms
        if self.csv_writer:
            self.csv_writer.writerow(
                [ts_ms, pkt.pkt_id, 'arrived', pkt.size_bytes,
                 pkt.delay_ms()])

    def reset(self):
        # tx host stats
        self.pkts_sent = 0
        self.bytes_sent = 0
        self.first_pkt_sent_ts_ms = -1
        self.pkt_sent_ts_ms = -1

        self.pkts_acked = 0
        self.bytes_acked = 0
        self.first_pkt_acked_ts_ms = -1
        self.pkt_acked_ts_ms = -1

        self.pkts_lost = 0
        self.bytes_lost = 0

        # rx host stats
        self.pkts_rcvd = 0
        self.bytes_rcvd = 0
        self.first_pkt_rcvd_ts_ms = -1
        self.pkt_rcvd_ts_ms = -1

    def summary(self):
        tx_rate_bytes_per_sec = self.bytes_sent * 1000 / \
                (self.pkt_sent_ts_ms - self.first_pkt_sent_ts_ms)
        rx_rate_bytes_per_sec = self.bytes_rcvd * 1000 / \
                (self.pkt_rcvd_ts_ms - self.first_pkt_rcvd_ts_ms)
        print(f"sending rate: {tx_rate_bytes_per_sec:.2f}B/s, {tx_rate_bytes_per_sec * 8 / 1e6:.2f}Mbps")
        print(f"recving rate: {rx_rate_bytes_per_sec:.2f}B/s, {rx_rate_bytes_per_sec * 8 / 1e6:.2f}Mbps")


class PacketLog():
    def __init__(self, pkt_sent_ts_ms: List[int], pkt_acked_ts_ms: List[int],
                 pkt_rtt_ms: List[int], pkt_queue_delays_ms: List[int],
                 first_ts_ms, binwise_bytes_sent: Dict[int, int],
                 binwise_bytes_acked: Dict[int, int],
                 binwise_bytes_lost: Dict[int, int],
                 packet_log_file: Optional[str] = None,
                 bin_size_ms: int = 500):
        self.pkt_log_file = packet_log_file
        self.pkt_sent_ts_ms = pkt_sent_ts_ms
        self.pkt_acked_ts_ms = pkt_acked_ts_ms
        self.pkt_rtt_ms = pkt_rtt_ms
        self.pkt_queue_delays_ms = pkt_queue_delays_ms
        self.bin_size_ms = bin_size_ms
        self.first_ts_ms = first_ts_ms

        self.binwise_bytes_sent = binwise_bytes_sent
        self.binwise_bytes_acked = binwise_bytes_acked
        self.binwise_bytes_lost = binwise_bytes_lost

        self.avg_sending_rate_mbps = None
        self.avg_tput_mbps = None
        self.avg_rtt_ms = None

    @classmethod
    def from_log_file(cls, packet_log_file: str, bin_size_ms: int = 500):
        pkt_sent_ts_ms = []
        pkt_acked_ts_ms = []
        pkt_rtt_ms = []
        pkt_queue_delays_ms = []
        first_ts_ms = None

        binwise_bytes_sent = {}
        binwise_bytes_acked = {}
        binwise_bytes_lost = {}
        with open(packet_log_file, 'r') as f:
            reader = csv.reader(f)
            for line in reader:
                if line[0] == 'timestamp_ms':
                    continue
                ts_ms = int(line[0])
                # pkt_id = int(line[1])
                pkt_type = line[2]
                pkt_byte = int(line[3])
                if first_ts_ms is None:
                    first_ts_ms = ts_ms
                # if ts - first_ts < 2:
                #     continue
                if pkt_type == Packet.ACK_PKT:
                    # one_queue_delay = float(line[4])
                    rtt_ms = int(line[4])
                    pkt_acked_ts_ms.append(ts_ms)
                    pkt_rtt_ms.append(rtt_ms)
                    # pkt_queue_delays.append(queue_delay)

                    bin_id = cls.ts_to_bin_id(ts_ms, first_ts_ms, bin_size_ms)
                    binwise_bytes_acked[bin_id] = binwise_bytes_acked.get(
                        bin_id, 0) + pkt_byte
                elif pkt_type == 'sent':
                    pkt_sent_ts_ms.append(ts_ms)
                    bin_id = cls.ts_to_bin_id(ts_ms, first_ts_ms, bin_size_ms)
                    binwise_bytes_sent[bin_id] = binwise_bytes_sent.get(
                        bin_id, 0) + pkt_byte
                elif pkt_type == 'lost':
                    bin_id = cls.ts_to_bin_id(ts_ms, first_ts_ms, bin_size_ms)
                    binwise_bytes_lost[bin_id] = binwise_bytes_lost.get(
                        bin_id, 0) + pkt_byte
                elif pkt_type == 'delivered':
                    pass
                else:
                    raise RuntimeError(
                        "Unrecognized pkt_type {}!".format(pkt_type))
        return cls(pkt_sent_ts_ms, pkt_acked_ts_ms, pkt_rtt_ms,
                   pkt_queue_delays_ms, first_ts_ms, binwise_bytes_sent,
                   binwise_bytes_acked, binwise_bytes_lost,
                   packet_log_file=packet_log_file, bin_size_ms=bin_size_ms)

    # @classmethod
    # def from_log(cls, pkt_log, ms_bin_size: int = 500):
    #     pkt_sent_ts = []
    #     pkt_acked_ts = []
    #     pkt_rtt = []
    #     pkt_queue_delays = []
    #     bin_size = ms_bin_size / 1000
    #     first_ts = None

    #     binwise_bytes_sent = {}
    #     binwise_bytes_acked = {}
    #     binwise_bytes_lost = {}
    #     first_ts = None
    #     for line in pkt_log:
    #         ts = line[0]
    #         pkt_id = line[1]
    #         pkt_type = line[2]
    #         pkt_byte = line[3]
    #         if first_ts is None:
    #             first_ts = ts
    #         if pkt_type == 'acked':
    #             rtt = float(line[4]) * 1000
    #             queue_delay = float(line[5]) * 1000
    #             pkt_acked_ts.append(ts)
    #             pkt_rtt.append(rtt)
    #             pkt_queue_delays.append(queue_delay)

    #             bin_id = cls.ts_to_bin_id(ts, first_ts, bin_size)
    #             binwise_bytes_acked[bin_id] = binwise_bytes_acked.get(
    #                 bin_id, 0) + pkt_byte
    #         elif pkt_type == 'sent':
    #             pkt_sent_ts.append(ts)
    #             bin_id = cls.ts_to_bin_id(ts, first_ts, bin_size)
    #             binwise_bytes_sent[bin_id] = binwise_bytes_sent.get(
    #                 bin_id, 0) + pkt_byte
    #         elif pkt_type == 'lost':
    #             bin_id = cls.ts_to_bin_id(ts, first_ts, bin_size)
    #             binwise_bytes_lost[bin_id] = binwise_bytes_lost.get(
    #                 bin_id, 0) + pkt_byte
    #         elif pkt_type == 'arrived':
    #             pass
    #         else:
    #             raise RuntimeError(
    #                 "Unrecognized pkt_type {}!".format(pkt_type))
    #     return cls(pkt_sent_ts, pkt_acked_ts, pkt_rtt, pkt_queue_delays,
    #                first_ts, binwise_bytes_sent, binwise_bytes_acked,
    #                binwise_bytes_lost, packet_log_file=None,
    #                bin_size_ms=ms_bin_size)

    @staticmethod
    def ts_to_bin_id(ts, first_ts, bin_size) -> int:
        return int((ts - first_ts) / bin_size)

    @staticmethod
    def bin_id_to_s(bin_id, bin_size) -> float:
        return (bin_id * bin_size) / 1e3

    def get_throughput_mbps(self) -> Tuple[List[float], List[float]]:
        ts_sec = []
        tput_mbps = []
        for bin_id in sorted(self.binwise_bytes_acked):
            ts_sec.append(self.bin_id_to_s(bin_id, self.bin_size_ms))
            tput_mbps.append(
                self.binwise_bytes_acked[bin_id] * BITS_PER_BYTE / self.bin_size_ms / 1e3)
        return ts_sec, tput_mbps

    def get_sending_rate_mbps(self) -> Tuple[List[float], List[float]]:
        ts_sec = []
        sending_rate_mbps = []
        for bin_id in sorted(self.binwise_bytes_sent):
            ts_sec.append(self.bin_id_to_s(bin_id, self.bin_size_ms))
            sending_rate_mbps.append(
                self.binwise_bytes_sent[bin_id] * BITS_PER_BYTE / self.bin_size_ms / 1e3)
        return ts_sec, sending_rate_mbps

    def get_rtt_ms(self) -> Tuple[List[float], List[int]]:
        return [ts_ms / 1e3 for ts_ms in self.pkt_acked_ts_ms], self.pkt_rtt_ms

    # def get_queue_delay_ms(self) -> Tuple[List[float], List[float]]:
    #     return self.pkt_acked_ts, self.pkt_queue_delays

    def get_loss_rate(self) -> float:
        return 1 - len(self.pkt_acked_ts_ms) / len(self.pkt_sent_ts_ms)

    # def get_reward(self, trace_file: str, trace=None) -> float:
    #     if trace_file and trace_file.endswith('.json'):
    #         trace = Trace.load_from_file(trace_file)
    #     elif trace_file and trace_file.endswith('.log'):
    #         trace = Trace.load_from_pantheon_file(trace_file, 0, 50, 500)
    #     loss = self.get_loss_rate()
    #     if trace is None:
    #         # original reward
    #         return pcc_aurora_reward(
    #             self.get_avg_throughput() * 1e6 / BITS_PER_BYTE / BYTES_PER_PACKET,
    #             self.get_avg_latency() / 1e3, loss)
    #     # normalized reward
    #     return pcc_aurora_reward(
    #         self.get_avg_throughput() * 1e6 / BITS_PER_BYTE / BYTES_PER_PACKET,
    #         self.get_avg_latency() / 1e3, loss,
    #         trace.avg_bw * 1e6 / BITS_PER_BYTE / BYTES_PER_PACKET,
    #         trace.min_delay * 2 / 1e3)

    def get_avg_sending_rate_mbps(self) -> float:
        if not self.pkt_sent_ts_ms:
            return 0.0
        if self.avg_sending_rate is None:
            dur_ms = self.pkt_sent_ts_ms[-1] - self.pkt_sent_ts_ms[0]
            bytes_sum = 0
            for _, bytes_sent in self.binwise_bytes_sent.items():
                bytes_sum += bytes_sent
            self.avg_sending_rate = bytes_sum * BITS_PER_BYTE / 1e3 / dur_ms
        return self.avg_sending_rate

    def get_avg_throughput_mbps(self) -> float:
        if not self.pkt_acked_ts_ms:
            return 0.0
        if self.avg_tput_mbps is None:
            dur_ms = self.pkt_acked_ts_ms[-1] - self.pkt_acked_ts_ms[0]
            bytes_sum = 0
            for _, bytes_acked in self.binwise_bytes_acked.items():
                bytes_sum += bytes_acked
            self.avg_tput_mbps = bytes_sum * BITS_PER_BYTE / 1e3 / dur_ms
        return self.avg_tput_mbps

    def get_avg_rtt_ms(self) -> float:
        if self.avg_rtt_ms is None:
            self.avg_rtt_ms = np.mean(self.pkt_rtt_ms)
        return self.avg_rtt_ms
