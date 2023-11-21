import warnings
warnings.filterwarnings("ignore")

import numpy as np
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

from gym import spaces
from stable_baselines.common.policies import FeedForwardPolicy


class MyMlpPolicy(FeedForwardPolicy):

    def __init__(self, sess, ob_space, ac_space, n_env, n_steps, n_batch,
                 reuse=False, **_kwargs):
        super(MyMlpPolicy, self).__init__(sess, ob_space, ac_space, n_env,
                                          n_steps, n_batch, reuse, net_arch=[
                                              {"pi": [32, 16], "vf": [32, 16]}],
                                          feature_extraction="mlp", **_kwargs)

    def step(self, obs, state=None, mask=None, deterministic=False, saliency=False):
        if deterministic:
            action, value, neglogp = self.sess.run([self.deterministic_action, self.value_flat, self.neglogp],
                                                   {self.obs_ph: obs})
            if saliency:
                grad = self.sess.run(tf.gradients(self.deterministic_action, self.obs_ph), {self.obs_ph: obs})[0]
                return action, value, self.initial_state, neglogp, grad

        else:
            action, value, neglogp = self.sess.run([self.action, self.value_flat, self.neglogp],
                                                   {self.obs_ph: obs})
        return action, value, self.initial_state, neglogp

class AuroraAgent:
    def __init__(self, model_path, observation_space, action_space) -> None:
        self.observation_space = observation_space
        self.action_space = action_space
        self.sess = tf.compat.v1.Session()
        self.policy = MyMlpPolicy(self.sess, observation_space, action_space, 1, 1, None)
        self.sess.run(tf.global_variables_initializer())
        if model_path:
            saver = tf.train.Saver()
            saver.restore(self.sess, model_path)

    def __del__(self):
        self.sess.close()

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
