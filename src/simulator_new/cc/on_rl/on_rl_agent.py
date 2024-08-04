import warnings
warnings.filterwarnings("ignore")

import numpy as np
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

from gym import spaces
from stable_baselines.common.policies import FeedForwardPolicy


class OnRLAgent:
    def __init__(self, policy, observation_space, action_space, model_path="") -> None:
        self.model_path = model_path
        self.observation_space = observation_space
        self.action_space = action_space
        self.policy = policy

    def __del__(self):
        if self.model_path and self.policy.sess:
            self.policy.sess.close()

    def predict(self, obs):
        obs = np.array(obs)
        actions, _, states, _ = self.policy.step(
            obs.reshape((-1,) + self.observation_space.shape), deterministic=True)

        clipped_actions = actions
        # Clip the actions to avoid out of bound error
        if isinstance(self.action_space, spaces.Box):
            clipped_actions = np.clip(actions, self.action_space.low, self.action_space.high)
        clipped_actions = clipped_actions[0]
        return clipped_actions, states

    @classmethod
    def from_model_path(cls, model_path, observation_space, action_space, layers=[64, 32]):
        sess = tf.compat.v1.Session()
        policy = FeedForwardPolicy(sess, observation_space, action_space, 1, 1, None, layers=layers, feature_extraction="mlp")
        sess.run(tf.global_variables_initializer())
        if model_path:
            saver = tf.train.Saver()
            saver.restore(sess, model_path)
        return cls(policy, observation_space, action_space, model_path)

    @classmethod
    def from_policy(cls, policy, observation_space, action_space):
        assert isinstance(policy, FeedForwardPolicy)
        return cls(policy, observation_space, action_space)
