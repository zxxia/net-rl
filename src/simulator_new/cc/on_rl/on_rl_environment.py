import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import gym
from gym.envs.registration import register
from gym.utils import seeding

from simulator_new.cc.pcc.aurora.trace_scheduler import TraceScheduler
from simulator_new.net_simulator import Simulator
from simulator_new.cc import OnRL


class OnRLEnvironment(gym.Env):

    def __init__(self, trace_scheduler: TraceScheduler, app='file_transfer', **kwargs):
        """Network environment used in simulation."""

        self.trace_scheduler = trace_scheduler
        self.trace = self.trace_scheduler.get_trace()

        self.simulator = Simulator(self.trace, "", "on_rl", app=app, lookup_table_path=kwargs['lookup_table_path'])
        assert isinstance(self.simulator.sender_cc, OnRL)

        # construct sender and network
        self.ts_ms = 0

        self.action_space = self.simulator.sender_cc.action_space
        self.observation_space = self.simulator.sender_cc.observation_space

    def seed(self, seed=None):
        self.rand, seed = seeding.np_random(seed)
        return [seed]

    def step(self, action):
        assert isinstance(self.simulator.sender_cc, OnRL)
        self.simulator.sender_cc.apply_action(action)
        while True:
            if self.simulator.sender_cc.new_rtcp:
                self.simulator.sender_cc.new_rtcp = False
                break
            self.ts_ms += 1
            self.simulator.tick(self.ts_ms)
        reward = self.simulator.sender_cc.reward
        obs = self.simulator.sender_cc.get_obs()

        should_stop = self.trace.is_finished(self.ts_ms / 1000)
        return obs, reward, should_stop, {}

    def reset(self):
        assert isinstance(self.simulator.sender_cc, OnRL)
        self.ts_ms = 0
        self.trace = self.trace_scheduler.get_trace()
        self.simulator.trace = self.trace
        self.simulator.reset()
        while True:
            if self.simulator.sender_cc.new_rtcp:
                self.simulator.sender_cc.new_rtcp = False
                break
            self.ts_ms += 1
            self.simulator.tick(self.ts_ms)
        obs = self.simulator.sender_cc.get_obs()
        return obs


register(id='OnRLEnv-v1', entry_point='simulator_new.cc.on_rl.on_rl_environment:OnRLEnvironment')
