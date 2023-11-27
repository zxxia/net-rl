import csv
import os

class StatsRecorder:
    def __init__(self, log_dir) -> None:
        self.log_dir = log_dir
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
            self.log_fh = open(os.path.join(log_dir, "pkt_log.csv"), 'w', 1)
            self.csv_writer = csv.writer(self.log_fh, lineterminator="\n")
            self.csv_writer.writerow(
                ["timestamp_ms", "pkt_id", "pkt_type", "size_bytes", "tot_delay_ms"])
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
                [ts_ms, pkt.pkt_id, pkt.pkt_type, pkt.size_bytes])

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
                [ts_ms, pkt.pkt_id, pkt.pkt_type, pkt.size_bytes,
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
