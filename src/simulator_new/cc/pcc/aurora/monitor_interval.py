import numpy as np

class MonitorInterval:
    # next_mi_id = 0


    def __init__(self,
                 pkts_sent=0,
                 pkts_acked=0,
                 pkts_lost=0,
                 bytes_sent=0,
                 bytes_acked=0,
                 bytes_lost=0,
                 send_start_ts_ms=0,
                 send_end_ts_ms=0,
                 recv_start_ts_ms=0,
                 recv_end_ts_ms=0,
                 rtt_ms_samples=[],
                 qdelay_ms_samples=[],
                 conn_min_avg_lat_ms=0,
                 last_pkt_bytes_sent=0) -> None:
        self.pkts_sent = pkts_sent
        self.pkts_acked = pkts_acked
        self.pkts_lost = pkts_lost
        self.bytes_sent = bytes_sent
        self.last_pkt_bytes_sent = last_pkt_bytes_sent
        self.bytes_acked = bytes_acked
        self.bytes_lost = bytes_lost
        self.send_start_ts_ms = send_start_ts_ms
        self.send_end_ts_ms = send_end_ts_ms
        self.recv_start_ts_ms = recv_start_ts_ms
        self.recv_end_ts_ms = recv_end_ts_ms
        self.rtt_ms_samples = rtt_ms_samples
        self.qdelay_ms_samples = qdelay_ms_samples
        self.conn_min_avg_lat_ms = conn_min_avg_lat_ms
        # self.mi_id = MonitorInterval.next_mi_id
        # MonitorInterval.next_mi_id += 1

        self.metric_map = {
            "send rate": (self.send_rate_bytes_per_sec, 0.0, 1500e9, 1500e7),
            "recv rate": (self.recv_rate_bytes_per_sec, 0.0, 1500e9, 1500e7),
            "recv dur": (self.recv_dur_ms, 0.0, 100000, 1),
            "send dur": (self.send_dur_ms, 0.0, 100000, 1),
            "avg latency": (self.avg_latency_ms, 0.0, 100000, 1),
            "avg queue delay": (self.avg_queue_delay_ms, 0.0, 100000, 1),
            "loss ratio": (self.loss_ratio, 0.0, 1.0, 1),
            "ack latency inflation": (self.ack_latency_inflation, -1.0, 10.0, 1),
            "sent latency inflation": (self.sent_latency_inflation, -1.0, 10.0, 1),
            "conn min latency": (self.conn_min_latency_ms, 0.0, 100000, 1),
            "latency increase": (self.latency_increase_ms, 0.0, 100000, 1),
            "latency ratio": (self.latency_ratio, 1.0, 10000.0, 1),
            "send ratio": (self.send_ratio, 0.0, 1000.0, 1),
            "recv ratio": (self.recv_ratio, 0.0, 1000.0, 1)}

    def get(self, feature):
        # print(self.metric_map[feature])
        func, min_val, max_val, scale = self.metric_map[feature]
        return func(), min_val, max_val, scale

    # Convert the observation parts of the monitor interval into a numpy array
    def as_array(self, features):
        vals = []
        for feat in features:
            val, _, _, scale = self.get(feat)
            vals.append(val / scale)
        return np.array(vals)

    def on_pkt_sent(self, ts_ms, pkt):
        # if self.bytes_sent == 0:
        #     # TODO: double check this line
        #     self.send_start_ts_ms = ts_ms
        self.send_end_ts_ms = ts_ms
        self.bytes_sent += pkt.size_bytes
        self.last_pkt_bytes_sent = pkt.size_bytes
        self.pkts_sent += 1

    def on_pkt_acked(self, ts_ms, pkt):
        # if self.bytes_acked == 0:
        #     self.recv_start_ts_ms = ts_ms
        self.recv_end_ts_ms = ts_ms
        self.bytes_acked += pkt.acked_size_bytes
        self.pkts_acked += 1
        self.rtt_ms_samples.append(pkt.rtt_ms())
        # TODO: get qdelay ms from ack pkt

    def on_pkt_lost(self, ts_ms, pkt):
        raise NotImplementedError

    def recv_dur_ms(self):
        return self.recv_end_ts_ms - self.recv_start_ts_ms

    def recv_rate_bytes_per_sec(self):
        dur_sec = self.recv_dur_ms() / 1000
        if dur_sec > 0.0:
            return self.bytes_acked / dur_sec
        return 0

    def avg_latency_ms(self):
        if len(self.rtt_ms_samples) > 0:
            return np.mean(self.rtt_ms_samples)
        return 0.0

    def avg_queue_delay_ms(self):
        if len(self.qdelay_ms_samples) > 0:
            return np.mean(self.qdelay_ms_samples)
        return 0.0

    def send_dur_ms(self):
        return self.send_end_ts_ms - self.send_start_ts_ms

    def send_rate_bytes_per_sec(self):
        dur_sec = self.send_dur_ms() / 1000
        if dur_sec > 0.0:
            return (self.bytes_sent - self.last_pkt_bytes_sent) / dur_sec
        return 0.0

    def loss_ratio(self):
        # This does not make sense
        if self.bytes_lost + self.bytes_acked > 0:
            return self.bytes_lost / (self.bytes_lost + self.bytes_acked)
        return 0.0

    def latency_increase_ms(self):
        half = int(len(self.rtt_ms_samples) / 2)
        if half >= 1:
            return np.mean(self.rtt_ms_samples[half:]) - np.mean(self.rtt_ms_samples[:half])
        return 0.0

    def ack_latency_inflation(self):
        dur_ms = self.recv_dur_ms()
        lat_inc_ms = self.latency_increase_ms()
        if dur_ms > 0.0:
            return lat_inc_ms / dur_ms
        return 0.0

    def sent_latency_inflation(self):
        dur_ms = self.send_dur_ms()
        lat_inc_ms = self.latency_increase_ms()
        if dur_ms > 0.0:
            return lat_inc_ms / dur_ms
        return 0.0

    def conn_min_latency_ms(self):
        avg_lat_ms = self.avg_latency_ms()
        if avg_lat_ms > 0 and self.conn_min_avg_lat_ms > 0:
            self.conn_min_avg_lat_ms = min(self.conn_min_avg_lat_ms, avg_lat_ms)
        elif self.conn_min_avg_lat_ms == 0:
            self.conn_min_avg_lat_ms = avg_lat_ms
        return self.conn_min_avg_lat_ms

    def send_ratio(self):
        thpt = self.recv_rate_bytes_per_sec()
        send_rate = self.send_rate_bytes_per_sec()
        if (thpt > 0.0) and (send_rate < 1000.0 * thpt):
            return send_rate / thpt
        # elif thpt == 0:
        #     return 2 #send_rate / 0.1
        return 1.0

    def recv_ratio(self):
        thpt = self.recv_rate_bytes_per_sec()
        send_rate = self.send_rate_bytes_per_sec()
        if send_rate == 0:
            return 1.0
        return thpt / send_rate

    def latency_ratio(self):
        min_lat = self.conn_min_latency_ms()
        cur_lat = self.avg_latency_ms()
        if min_lat > 0.0:
            return cur_lat / min_lat
        return 1.0


class MonitorIntervalHistory():
    def __init__(self, length, features):
        self.length = length
        self.features = features
        self.values = []
        # self.sender_id = sender_id
        for _ in range(0, length):
            self.values.append(MonitorInterval())

    def step(self, new_mi):
        self.values.pop(0)
        self.values.append(new_mi)

    def as_array(self):
        arrays = []
        for mi in self.values:
            arrays.append(mi.as_array(self.features))
        arrays = np.array(arrays).flatten()
        return arrays

    def back(self):
        return self.values[-1]

    def get_min_max_obs_vectors(self):
        min_vals = []
        max_vals = []
        for feature_name in self.features:
            val, min_val, max_val, scale = self.values[-1].get(feature_name)
            min_vals.append(min_val)
            max_vals.append(max_val)
        min_obs_vec = np.tile(np.array(min_vals), self.length)
        max_obs_vec = np.tile(np.array(max_vals), self.length)
        return min_obs_vec, max_obs_vec
