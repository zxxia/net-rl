import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import gym
from gym.envs.registration import register
from gym.utils import seeding

from simulator_new.cc.pcc.aurora.trace_scheduler import TraceScheduler
from simulator_new.net_simulator import Simulator
from simulator_new.cc import Aurora


class AuroraEnvironment(gym.Env):

    def __init__(self, trace_scheduler: TraceScheduler):
        """Network environment used in simulation."""

        self.trace_scheduler = trace_scheduler
        self.trace = self.trace_scheduler.get_trace()

        self.simulator = Simulator(self.trace, "", "aurora")
        assert isinstance(self.simulator.sender_cc, Aurora)

        # construct sender and network
        self.ts_ms = 0

        self.action_space = self.simulator.sender_cc.action_space
        self.observation_space = self.simulator.sender_cc.observation_space

    def seed(self, seed=None):
        self.rand, seed = seeding.np_random(seed)
        return [seed]

    def step(self, action):
        assert isinstance(self.simulator.sender_cc, Aurora)
        self.simulator.sender_cc.apply_rate_delta(action)
        prev_mi_id = self.simulator.sender_cc.mi_history.back().mi_id
        while self.simulator.sender_cc.mi_history.back().mi_id <= prev_mi_id:
            self.ts_ms += 1
            self.simulator.tick(self.ts_ms)
        reward = self.simulator.sender_cc.reward
        obs = self.simulator.sender_cc.get_obs()

        should_stop = self.trace.is_finished(self.ts_ms)

        return obs, reward, should_stop, {}

    def reset(self):
        assert isinstance(self.simulator.sender_cc, Aurora)
        self.ts_ms = 0
        self.trace = self.trace_scheduler.get_trace()
        self.simulator.trace = self.trace
        self.simulator.reset()
        prev_mi_id = self.simulator.sender_cc.mi_history.back().mi_id
        while self.simulator.sender_cc.mi_history.back().mi_id <= prev_mi_id:
            self.ts_ms += 1
            self.simulator.tick(self.ts_ms)
        return self.simulator.sender_cc.get_obs()


register(id='AuroraEnv-v1', entry_point='simulator_new.cc.pcc.aurora.aurora_environment:AuroraEnvironment')
