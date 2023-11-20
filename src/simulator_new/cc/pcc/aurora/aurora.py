from typing import List, Optional

import numpy as np
from gym import spaces

from simulator_new.cc import CongestionControl
from simulator_new.cc.pcc.aurora.monitor_interval import MonitorInterval, MonitorIntervalHistory
from simulator_new.cc.pcc.aurora.aurora_agent import AuroraAgent
from simulator_new.constant import MSS


def pcc_aurora_reward(tput_pkt_per_sec: float, delay_sec: float, loss: float,
                      avg_bw_pkt_per_sec: Optional[float] = None,
                      min_rtt_sec: Optional[float] = None) -> float:
    """PCC Aurora reward. Anchor point 0.6Mbps
    throughput: packets per second
    delay: second
    loss:
    avg_bw: packets per second
    """
    # if avg_bw is not None and min_rtt is not None:
    #     return 10 * 50 * throughput/avg_bw - 1000 * delay * 0.2 / min_rtt - 2000 * loss
    if avg_bw_pkt_per_sec is not None:
        return 10 * 50 * tput_pkt_per_sec/avg_bw_pkt_per_sec - 1000 * delay_sec - 2000 * loss
    return 10 * tput_pkt_per_sec - 1000 * delay_sec - 2000 * loss

class Aurora(CongestionControl):

    MAX_RATE_BYTES_PER_SEC = 30000000  # 240Mbps
    MIN_RATE_BYTES_PER_SEC = 7500  # 0.06Mbps

    def __init__(self, model_path: str, history_len: int = 10,
                 features: List[str] = ["sent latency inflation",
                                        "latency ratio", "recv ratio"]) -> None:
        super().__init__()
        self.model_path = model_path
        self.features = features
        self.history_len = history_len

        self.mi_duration_ms = 10
        self.mi_end_ts_ms = 10
        self.mi_history = MonitorIntervalHistory(history_len, features)
        self.mi = MonitorInterval()
        self.reward = 0
        min_obs_vec, max_obs_vec = self.mi_history.get_min_max_obs_vectors()
        self.observation_space = spaces.Box(
            min_obs_vec, max_obs_vec, dtype=np.float32)
        self.action_space = spaces.Box(np.array([-1e12]), np.array([1e12]), dtype=np.float32)

        if self.model_path:
            self.agent = AuroraAgent(model_path, self.observation_space, self.action_space)
        else:
            self.agent = None

    def on_pkt_sent(self, ts_ms, pkt):
        self.mi.on_pkt_sent(ts_ms, pkt)

    def on_pkt_acked(self, ts_ms, pkt):
        self.mi.on_pkt_acked(ts_ms, pkt)

    def tick(self, ts_ms):
        if ts_ms >= self.mi_end_ts_ms:
            self._on_mi_finish(ts_ms)
            obs = self.get_obs()  # obtain the observation vector
            if self.agent:
                action, _ = self.agent.predict(obs)
                # make decision here
                self.apply_rate_delta(action[0])

    def reset(self):
        self.mi_duration_ms = 10
        self.mi_end_ts_ms = 10
        self.mi_history = MonitorIntervalHistory(self.history_len, self.features)
        self.mi = MonitorInterval()
        self.reward = 0

    def apply_rate_delta(self, delta):
        assert self.host
        delta = float(delta)
        if delta >= 0.0:
            self.set_rate(self.host.pacing_rate_bytes_per_sec * (1.0 + delta))
        else:
            self.set_rate(self.host.pacing_rate_bytes_per_sec / (1.0 - delta))

    def set_rate(self, pacing_rate_bytes_per_sec):
        assert self.host
        pacing_rate_bytes_per_sec = min(Aurora.MAX_RATE_BYTES_PER_SEC,
                                        pacing_rate_bytes_per_sec)
        pacing_rate_bytes_per_sec = max(Aurora.MIN_RATE_BYTES_PER_SEC,
                                        pacing_rate_bytes_per_sec)
        self.host.pacing_rate_bytes_per_sec = pacing_rate_bytes_per_sec

    def get_obs(self):
        return self.mi_history.as_array()

    def _on_mi_finish(self, ts_ms):
        # compute reward
        tput, _, _, _ = self.mi.get("recv rate")  # bytes/sec
        lat, _, _, _ = self.mi.get("avg latency")  # ms
        loss, _, _, _ = self.mi.get("loss ratio")
        self.reward = pcc_aurora_reward(tput / MSS, lat, loss)

        self.mi_duration_ms = lat  # set next mi duration
        self.mi_end_ts_ms = ts_ms + self.mi_duration_ms

        self.mi_history.step(self.mi) # append current mi to mi history
        # create a new mi
        self.mi = MonitorInterval(
            pkts_sent=1,
            bytes_sent=self.mi.last_pkt_bytes_sent,
            send_start_ts_ms=self.mi.send_end_ts_ms,
            recv_start_ts_ms=self.mi.recv_end_ts_ms,
            conn_min_avg_lat_ms=self.mi.conn_min_latency_ms(),
            last_pkt_bytes_sent=self.mi.last_pkt_bytes_sent)
