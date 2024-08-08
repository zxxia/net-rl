import copy
import csv
import os

import numpy as np
from gym import spaces

from simulator_new.cc import CongestionControl
from simulator_new.cc.on_rl.on_rl_agent import OnRLAgent
from simulator_new.constant import MSS

def compute_reward(tput, owd, loss) -> float:
    alpha, beta, eta, phi = 200, 50, 10, 30
    reward = alpha * np.sum(tput) - beta * np.sum(loss) - \
            eta * np.sum(owd) # - phi * np.sum(np.abs(np.ediff1d(tput)))
    # reward = alpha * np.sum(obs[:, 3]) - beta * np.sum(obs[:, 0]) - \
    #         eta * np.sum(obs[:, 1]) - phi * np.sum(np.abs(np.ediff1d(obs[:, 3])))
    # reward = alpha * np.sum(obs[:, 2]) - beta * np.sum(obs[:, 0]) - \
    #         eta * np.sum(obs[:, 1]) - phi * np.sum(np.abs(np.ediff1d(obs[:, 2])))
    return reward

class OnRL(CongestionControl):

    # MAX_RATE_BYTE_PER_SEC = 30000000  # 240Mbps
    MAX_RATE_BYTE_PER_SEC = 1500000  # 12Mbps
    # MIN_RATE_BYTE_PER_SEC = 7500  # 0.06Mbps
    MIN_RATE_BYTE_PER_SEC = 62500  # 0.06Mbps
    START_PACING_RATE_BYTE_PER_SEC = 10 * MSS / 0.05
    ACTION_SPACE = np.arange(0.1, 4.1, 0.1) # Mbps
    # State range:
    MIN_LOSS_RATE, MAX_LOSS_RATE = 0.0, 1.0
    MIN_OWD_MS, MAX_OWD_MS = 0.0, 1e12
    MIN_DELAY_INTERVAL_MS, MAX_DELAY_INTERVAL_MS = -1e12, 1e12
    MIN_TPUT_MBPS, MAX_TPUT_MBPS = 0.0, 1e12

    def __init__(self, model_path: str, history_len: int = 5, save_dir: str ="") -> None:
        super().__init__()
        self.save_dir = save_dir
        if self.save_dir:
            os.makedirs(save_dir, exist_ok=True)
            self.log_path = os.path.join(self.save_dir, 'on_rl_log.csv')
            self.log = open(self.log_path, 'w', 1)
            self.csv_writer = csv.writer(self.log, lineterminator='\n')
            self.csv_writer.writerow(
                ['timestamp_ms', "pacing_rate_Bps", "est_rate_Bps", 'tput_Bps',
                 'owd_ms', "loss_fraction", "delay_interval_ms", 'reward',
                 "action", "queue_delay", 'pkt_in_queue', 'bytes_in_queue',
                 "queue_capacity_bytes"])
        else:
            self.log_path = None
            self.log = None
            self.csv_writer = None
        self.model_path = model_path
        self.history_len = history_len

        self.reward = 0

        self.observation_space = spaces.Box(
            np.repeat([[self.MIN_LOSS_RATE, self.MIN_OWD_MS,
                      # self.MIN_DELAY_INTERVAL_MS,
                     # self.MIN_TPUT_MBPS,
                        self.MIN_TPUT_MBPS]],
                      self.history_len, axis=0).ravel(),
            np.repeat([[self.MAX_LOSS_RATE, self.MAX_OWD_MS,
                      # self.MAX_DELAY_INTERVAL_MS,
                     # self.MAX_TPUT_MBPS,
                        self.MAX_TPUT_MBPS]],
                      self.history_len, axis=0).ravel(),
            dtype=np.float32)

        self.action_space = spaces.Discrete(len(self.ACTION_SPACE))

        if self.model_path:
            self.agent = OnRLAgent.from_model_path(
                model_path, self.observation_space, self.action_space)
        else:
            self.agent = None
            # self.agent = OnRLAgent.from_model_path("", self.observation_space,
            #                                        self.action_space)

        self.est_rate_Bps = OnRL.START_PACING_RATE_BYTE_PER_SEC
        self.obs = np.zeros((self.history_len, 4))
        self.obs[:, 3] = self.est_rate_Bps * 8e-6
        # self.obs = np.zeros((self.history_len, 3))
        self.new_rtcp = False
        self.min_delay = 1e12

    def __del__(self):
        if self.log:
            self.log.close()

    def register_host(self, host):
        super().register_host(host)

    def register_policy(self, policy):
        self.agent = OnRLAgent.from_policy(
            policy, self.observation_space, self.action_space)

    def get_est_rate_Bps(self, start_ts_ms, end_ts_ms):
        return self.est_rate_Bps

    def on_pkt_sent(self, ts_ms, pkt):
        pass

    def on_pkt_rcvd(self, ts_ms, pkt):
        # on rtcp rcvd, run model and apply the decision
        if pkt.is_rtcp_pkt():
            self.obs = np.roll(self.obs, -1, axis=0)
            self.min_delay = min(pkt.owd_ms, self.min_delay)
            self.obs[-1] = np.array([pkt.loss_fraction, pkt.owd_ms, # pkt.delay_interval_ms,
                                     pkt.tput_Bps * 8e-6, self.est_rate_Bps * 8e-6])
            feat = copy.deepcopy(self.obs[:, 0:3])
            feat[:, 1] /= self.min_delay
            feat[:, 2] /= self.obs[:, 3]

            # loss, owd, jitter, tput, send_rate = self.obs[:, 0], \
            #     self.obs[:, 1], self.obs[:, 2], self.obs[:, 3], self.obs[:, 4]
            loss, owd,  tput, send_rate = self.obs[:, 0], \
                self.obs[:, 1], self.obs[:, 2], self.obs[:, 3]
            self.reward = compute_reward(tput, owd, loss)
            if self.agent:
                # action, _ = self.agent.predict(self.obs)
                action, _ = self.agent.predict(feat.ravel())
            else:
                action = None

            if self.csv_writer and self.host:
                self.csv_writer.writerow(
                    [ts_ms, self.host.pacer.pacing_rate_Bps, self.est_rate_Bps,
                     pkt.tput_Bps, pkt.owd_ms, pkt.loss_fraction,
                     pkt.delay_interval_ms, self.reward, action,
                     0,  # queue delay
                     len(self.host.tx_link.queue),
                     self.host.tx_link.queue_size_bytes,
                     self.host.tx_link.queue_cap_bytes])
            self.apply_action(action)
            self.new_rtcp = True

    def on_pkt_lost(self, ts_ms, pkt):
        pass

    def tick(self, ts_ms):
        pass

    def reset(self):
        self.reward = 0
        self.est_rate_Bps = OnRL.START_PACING_RATE_BYTE_PER_SEC
        self.obs = np.zeros((self.history_len, 4))
        self.obs[:, 3] = self.est_rate_Bps * 8e-6
        self.new_rtcp = False
        self.min_delay = 1e12

    def apply_action(self, action):
        if action is None:
            return
        assert self.host
        self.est_rate_Bps = self.ACTION_SPACE[action] * 1e6 / 8
        self.est_rate_Bps = max(
            OnRL.MIN_RATE_BYTE_PER_SEC,
            min(OnRL.MAX_RATE_BYTE_PER_SEC, self.est_rate_Bps))

    def get_obs(self):
        feat = copy.deepcopy(self.obs[:, 0:3])
        feat[:, 2] /= self.obs[:, 3]
        return feat.ravel()
        # return self.obs
