import argparse
import csv
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ""
import time
import types
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

from typing import List

import numpy as np
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

import gym
import pandas as pd
from mpi4py.MPI import COMM_WORLD
from stable_baselines import PPO1
from stable_baselines.common.callbacks import BaseCallback

from simulator_new.net_simulator import Simulator
from simulator_new.cc.pcc.aurora import aurora_environment
from simulator_new.cc.pcc.aurora.aurora_agent import MyMlpPolicy
from simulator_new.cc.pcc.aurora.trace_scheduler import TraceScheduler, UDRTrainScheduler
from simulator_new.trace import Trace, generate_traces
from simulator_new.utils import set_seed, save_args


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
                 verbose=0, steps_trained=0, app='file_transfer'):
        super(SaveOnBestTrainingRewardCallback, self).__init__(verbose)
        self.check_freq = check_freq
        self.save_path = log_dir
        self.best_mean_reward = -np.inf
        self.val_traces = val_traces
        if COMM_WORLD.Get_rank() == 0:
            os.makedirs(self.save_path, exist_ok=True)
            self.val_log_writer = csv.writer(
                open(os.path.join(self.save_path, 'validation_log.csv'), 'w', 1),
                delimiter='\t', lineterminator='\n')
            self.val_log_writer.writerow(
                ['n_calls', 'num_timesteps', 'mean_validation_reward',
                 'mean_validation_pkt_level_reward', 'loss',
                 'throughput', 'latency', 'sending_rate', 'tot_t_used(min)',
                 'val_t_used(min)', 'train_t_used(min)'])

            val_trace_dir = os.path.join(self.save_path, "validation_traces")

            os.makedirs(val_trace_dir, exist_ok=True)
            for i, tr in enumerate(self.val_traces):
                tr.dump(os.path.join(val_trace_dir, "trace_{}.json".format(i)))
        else:
            self.val_log_writer = None
        self.best_val_reward = -np.inf
        self.val_times = 0

        self.t_start = time.time()
        self.prev_t = time.time()
        self.steps_trained = steps_trained
        self.app = app

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
                avg_tr_bw = []
                avg_tr_min_rtt = []
                avg_tr_loss = []
                avg_rewards = []
                avg_pkt_level_rewards = []
                avg_losses = []
                avg_tputs = []
                avg_delays = []
                avg_send_rates = []
                val_start_t = time.time()

                for idx, val_trace in enumerate(self.val_traces):

                    # lookup_table = "./AE_lookup_table/segment_0vu1_dwHF7g_480x360.mp4.csv"
                    lookup_table = None
                    val_sim_dir = os.path.join(self.save_path, f"step_{int(self.num_timesteps)}", f"val_trace_{idx}")
                    os.makedirs(val_sim_dir, exist_ok=True)
                    val_sim = Simulator(val_trace, val_sim_dir, "aurora", app=self.app,
                                        model_path=None, lookup_table_path=lookup_table)
                    val_sim.sender_cc.register_policy(self.model.policy_pi)
                    val_sim.simulate(int(val_trace.duration), True)
                    avg_tr_bw.append(val_trace.avg_bw)
                    avg_tr_min_rtt.append(val_trace.avg_bw)
                    df = pd.read_csv(os.path.join(val_sim_dir, 'aurora_mi_log.csv'))
                    avg_rewards.append(df['reward'].mean())
                    avg_losses.append(df['loss_ratio'].mean())
                    avg_tputs.append(df['recv_rate_Bps'].mean())
                    avg_delays.append(df['latency_ms'].mean())
                    avg_send_rates.append(df['send_rate_Bps'].mean())

                cur_t = time.time()
                self.val_log_writer.writerow(
                    map(lambda t: "%.3f" % t,
                        [float(self.n_calls), float(self.num_timesteps),
                         np.mean(np.array(avg_rewards)),
                         np.mean(np.array(avg_pkt_level_rewards)),
                         np.mean(np.array(avg_losses)),
                         np.mean(np.array(avg_tputs)),
                         np.mean(np.array(avg_delays)),
                         np.mean(np.array(avg_send_rates)),
                         (cur_t - self.t_start) / 60,
                         (cur_t - val_start_t) / 60, (val_start_t - self.prev_t) / 60]))
                self.prev_t = cur_t
        return True


def train_aurora(train_scheduler: TraceScheduler, config_file: str,
                 total_timesteps: int, seed: int, log_dir: str,
                 timesteps_per_actorbatch: int, model_path: str = "",
                 tb_log_name: str = "", validation_traces: List[Trace] = [],
                 tensorboard_log=None, app='file_transfer', lookup_table_path='') -> None:
    env = gym.make('AuroraEnv-v1', trace_scheduler=train_scheduler,
                   app=app, lookup_table_path=lookup_table_path)
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
        steps_trained=steps_trained, val_traces=validation_traces, app=app)
    model.learn(total_timesteps=total_timesteps, tb_log_name=tb_log_name,
                callback=callback)


def parse_args():
    """Parse arguments from the command line."""
    parser = argparse.ArgumentParser("Training code.")
    parser.add_argument(
        "--exp-name", type=str, default="", help="Experiment name."
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        required=True,
        help="direcotry to save the model.",
    )
    parser.add_argument("--seed", type=int, default=20, help="seed")
    parser.add_argument(
        "--total-timesteps",
        type=int,
        default=100,
        help="Total number of steps to be trained.",
    )
    parser.add_argument(
        "--pretrained-model-path",
        type=str,
        default="",
        help="Path to a pretrained Tensorflow checkpoint!",
    )
    parser.add_argument(
        "--app",
        type=str,
        required=True,
        choices=("file_transfer", "video_streaming"),
        help="Path to an autoencoder lookup table on a video.",
    )
    parser.add_argument(
        "--lookup-table",
        type=str,
        default="",
        help="Path to an autoencoder lookup table on a video.",
    )
    parser.add_argument(
        "--tensorboard-log",
        type=str,
        default=None,
        help="tensorboard log direcotry.",
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="specify to enable validation.",
    )
    parser.add_argument(
        "--val-freq",
        type=int,
        default=7200,
        help="specify to enable validation.",
    )
    subparsers = parser.add_subparsers(dest="curriculum", help="CL parsers.")
    udr_parser = subparsers.add_parser("udr", help="udr")
    udr_parser.add_argument(
        "--real-trace-prob",
        type=float,
        default=0.0,
        help="Probability of picking a real trace in training",
    )
    udr_parser.add_argument(
        "--train-trace-file",
        type=str,
        default="",
        help="A file contains a list of paths to the training traces.",
    )
    udr_parser.add_argument(
        "--val-trace-file",
        type=str,
        default="",
        help="A file contains a list of paths to the validation traces.",
    )
    udr_parser.add_argument(
        "--config-file",
        type=str,
        default="",
        help="A json file which contains a list of randomization ranges with "
        "their probabilites.",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="pantheon",
        choices=("pantheon", "synthetic"),
        help="dataset name",
    )
    # cl1_parser = subparsers.add_parser("cl1", help="cl1")
    # cl1_parser.add_argument(
    #     "--config-files",
    #     type=str,
    #     nargs="+",
    #     help="A list of randomization config files.",
    # )
    # cl2_parser = subparsers.add_parser("cl2", help="cl2")
    # cl2_parser.add_argument(
    #     "--baseline",
    #     type=str,
    #     required=True,
    #     choices=("bbr", "bbr_old", "cubic"),
    #     help="Baseline used to sort environments.",
    # )
    # cl2_parser.add_argument(
    #     "--config-file",
    #     type=str,
    #     default="",
    #     help="A json file which contains a list of randomization ranges with "
    #     "their probabilites.",
    # )

    return parser.parse_args()


def main():
    args = parse_args()
    assert (
        not args.pretrained_model_path
        or args.pretrained_model_path.endswith(".ckpt")
    )
    os.makedirs(args.save_dir, exist_ok=True)
    save_args(args, args.save_dir)
    set_seed(args.seed + COMM_WORLD.Get_rank() * 100)
    nprocs = COMM_WORLD.Get_size()

    # training_traces, validation_traces
    training_traces = []
    val_traces = []
    if args.curriculum == "udr":
        config_file = args.config_file
        if args.train_trace_file:
            with open(args.train_trace_file, "r") as f:
                for line in f:
                    line = line.strip()
                    training_traces.append(Trace.load_from_file(line))

        if args.validation and args.val_trace_file:
            with open(args.val_trace_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if args.dataset == "pantheon":
                        queue = 100  # dummy value
                        val_traces.append(
                            Trace.load_from_pantheon_file(
                                line, queue=queue, loss=0
                            )
                        )
                    elif args.dataset == "synthetic":
                        val_traces.append(Trace.load_from_file(line))
                    else:
                        raise ValueError
        train_scheduler = UDRTrainScheduler(
            config_file,
            training_traces,
            percent=args.real_trace_prob,
        )
    # elif args.curriculum == "cl1":
    #     config_file = args.config_files[0]
    #     train_scheduler = CL1TrainScheduler(args.config_files, aurora)
    # elif args.curriculum == "cl2":
    #     config_file = args.config_file
    #     train_scheduler = CL2TrainScheduler(
    #         config_file, aurora, args.baseline
    #     )
    else:
        raise NotImplementedError

    train_aurora(
        train_scheduler,
        config_file,
        args.total_timesteps,
        args.seed + COMM_WORLD.Get_rank() * 100,
        args.save_dir,
        int(args.val_freq / nprocs),
        args.pretrained_model_path,
        tb_log_name=args.exp_name,
        validation_traces=val_traces,
        tensorboard_log=args.tensorboard_log,
        app=args.app,
        lookup_table_path=args.lookup_table,
    )


if __name__ == "__main__":
    t_start = time.time()
    main()
    print("time used: {:.2f}s".format(time.time() - t_start))
