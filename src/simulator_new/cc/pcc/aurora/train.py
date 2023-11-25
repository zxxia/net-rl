import csv
import os
import time
import types
from typing import List

import numpy as np
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

import gym
from mpi4py.MPI import COMM_WORLD
from stable_baselines import PPO1
from stable_baselines.common.callbacks import BaseCallback

from simulator_new.cc.pcc.aurora import aurora_environment
from simulator_new.cc.pcc.aurora.aurora_agent import MyMlpPolicy
from simulator_new.cc.pcc.aurora.trace_scheduler import TraceScheduler
from simulator_new.trace import Trace, generate_traces


if type(tf.contrib) != types.ModuleType:  # if it is LazyLoader
    tf.contrib._warning = None

class MyPPO1(PPO1):

    def predict(self, observation, state=None, mask=None, deterministic=False, saliency=False):
        if state is None:
            state = self.initial_state
        if mask is None:
            mask = [False for _ in range(self.n_envs)]
        observation = np.array(observation)
        vectorized_env = self._is_vectorized_observation(observation, self.observation_space)

        observation = observation.reshape((-1,) + self.observation_space.shape)
        grad = None
        if deterministic and saliency:
            actions, _, states, _, grad = self.step(observation, state, mask, deterministic=deterministic, saliency=saliency)
        else:
            actions, _, states, _ = self.step(observation, state, mask, deterministic=deterministic)

        clipped_actions = actions
        # Clip the actions to avoid out of bound error
        if isinstance(self.action_space, gym.spaces.Box):
            clipped_actions = np.clip(actions, self.action_space.low, self.action_space.high)

        if not vectorized_env:
            if state is not None:
                raise ValueError("Error: The environment must be vectorized when using recurrent policies.")
            clipped_actions = clipped_actions[0]

        if deterministic and saliency:
            return clipped_actions, states, grad
        elif deterministic and saliency:
            return clipped_actions, states
        else:
            return clipped_actions, states


class SaveOnBestTrainingRewardCallback(BaseCallback):
    """
    Callback for saving a model (the check is done every ``check_freq`` steps)
    based on the training reward (in practice, we recommend using
    ``EvalCallback``).

    :param check_freq: (int)
    :param log_dir: (str) Path to the folder where the model will be saved.
      It must contains the file created by the ``Monitor`` wrapper.
    :param verbose: (int)
    """

    def __init__(self, check_freq: int, log_dir: str, val_traces: List[Trace] = [],
                 verbose=0, steps_trained=0):
        super(SaveOnBestTrainingRewardCallback, self).__init__(verbose)
        self.check_freq = check_freq
        self.log_dir = log_dir
        self.save_path = log_dir
        self.best_mean_reward = -np.inf
        self.val_traces = val_traces
        if COMM_WORLD.Get_rank() == 0:
            os.makedirs(log_dir, exist_ok=True)
            self.val_log_writer = csv.writer(
                open(os.path.join(log_dir, 'validation_log.csv'), 'w', 1),
                delimiter='\t', lineterminator='\n')
            self.val_log_writer.writerow(
                ['n_calls', 'num_timesteps', 'mean_validation_reward',
                 'mean_validation_pkt_level_reward', 'loss',
                 'throughput', 'latency', 'sending_rate', 'tot_t_used(min)',
                 'val_t_used(min)', 'train_t_used(min)'])

            os.makedirs(os.path.join(log_dir, "validation_traces"), exist_ok=True)
            for i, tr in enumerate(self.val_traces):
                tr.dump(os.path.join(log_dir, "validation_traces", "trace_{}.json".format(i)))
        else:
            self.val_log_writer = None
        self.best_val_reward = -np.inf
        self.val_times = 0

        self.t_start = time.time()
        self.prev_t = time.time()
        self.steps_trained = steps_trained

    def _init_callback(self) -> None:
        # Create folder if needed
        if self.save_path is not None:
            os.makedirs(self.save_path, exist_ok=True)

    def _on_step(self) -> bool:
        if self.n_calls % self.check_freq == 0:

            if COMM_WORLD.Get_rank() == 0 and self.val_log_writer is not None:
                model_path_to_save = os.path.join(
                    self.save_path,
                    "model_step_{}.ckpt".format(int(self.num_timesteps)))
                with self.model.graph.as_default():
                    saver = tf.train.Saver()
                    saver.save(self.model.sess, model_path_to_save)
                if not self.val_traces:
                    return True
                # avg_tr_bw = []
                # avg_tr_min_rtt = []
                # avg_tr_loss = []
                # avg_rewards = []
                # avg_pkt_level_rewards = []
                # avg_losses = []
                # avg_tputs = []
                # avg_delays = []
                # avg_send_rates = []
                # val_start_t = time.time()

                # for idx, val_trace in enumerate(self.val_traces):
                #     avg_tr_bw.append(val_trace.avg_bw)
                #     avg_tr_min_rtt.append(val_trace.avg_bw)
                #     ts_list, val_rewards, loss_list, tput_list, delay_list, \
                #         send_rate_list, action_list, obs_list, mi_list, pkt_level_reward = self.aurora._test(
                #             val_trace, self.log_dir)
                #     avg_rewards.append(np.mean(np.array(val_rewards)))
                #     avg_losses.append(np.mean(np.array(loss_list)))
                #     avg_tputs.append(float(np.mean(np.array(tput_list))))
                #     avg_delays.append(np.mean(np.array(delay_list)))
                #     avg_send_rates.append(
                #         float(np.mean(np.array(send_rate_list))))
                #     avg_pkt_level_rewards.append(pkt_level_reward)
                # cur_t = time.time()
                # self.val_log_writer.writerow(
                #     map(lambda t: "%.3f" % t,
                #         [float(self.n_calls), float(self.num_timesteps),
                #          np.mean(np.array(avg_rewards)),
                #          np.mean(np.array(avg_pkt_level_rewards)),
                #          np.mean(np.array(avg_losses)),
                #          np.mean(np.array(avg_tputs)),
                #          np.mean(np.array(avg_delays)),
                #          np.mean(np.array(avg_send_rates)),
                #          (cur_t - self.t_start) / 60,
                #          (cur_t - val_start_t) / 60, (val_start_t - self.prev_t) / 60]))
                # self.prev_t = cur_t
        return True


def train_aurora(train_scheduler: TraceScheduler, config_file: str,
                 total_timesteps: int, seed: int, log_dir: str,
                 timesteps_per_actorbatch: int, model_path: str = "",
                 tb_log_name: str = "", validation_traces: List[Trace] = [],
                 tensorboard_log=None) -> None:
    env = gym.make('AuroraEnv-v1', trace_scheduler=train_scheduler)
    env.seed(seed)
    model = MyPPO1(MyMlpPolicy, env, verbose=1, seed=seed,
                        optim_stepsize=0.001, schedule='constant',
                        timesteps_per_actorbatch=timesteps_per_actorbatch,
                        optim_batchsize=int(timesteps_per_actorbatch/12),
                        optim_epochs=12, gamma=0.99,
                        tensorboard_log=tensorboard_log, n_cpu_tf_sess=1)

    steps_trained = 0
    if model_path:
        with model.graph.as_default():
            saver = tf.train.Saver()
            saver.restore(model.sess, model_path)
        try:
            steps_trained = int(os.path.splitext(model_path)[0].split('_')[-1])
        except:
            pass

    # generate validation traces
    if not validation_traces and config_file:
        validation_traces = generate_traces(
            config_file, 20, duration=30)

    callback = SaveOnBestTrainingRewardCallback(
        check_freq=timesteps_per_actorbatch, log_dir=log_dir,
        steps_trained=steps_trained, val_traces=validation_traces)
    model.learn(total_timesteps=total_timesteps, tb_log_name=tb_log_name,
                callback=callback)
