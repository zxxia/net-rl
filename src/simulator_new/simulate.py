import argparse
import time

# import numpy as np

from simulator_new.net_simulator import Simulator
from simulator_new.trace import Trace, generate_trace



def parse_args():
    parser = argparse.ArgumentParser("Simulate")
    parser.add_argument(
        '--trace',
        type=str,
        default="",
        help="A network trace file.",
    )
    parser.add_argument(
        "--lookup-table",
        type=str,
        default="./AE_lookup_table/segment_3IY83M-m6is_480x360.mp4.csv",
        help="A look up table file.",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default=".",
        help="A direcotry to save the results.",
    )
    parser.add_argument(
        "--cc",
        type=str,
        default="gcc",
        choices=("aurora", "bbr", "gcc", 'oracle', 'oracle_no_predict'),
        help="Congestion control.",
    )
    parser.add_argument(
        '--app',
        type=str,
        default="video_streaming",
        choices=("file_transfer", "video_streaming"),
        help="Appliaction",
    )
    parser.add_argument(
        '--model',
        type=str,
        default="",
        help='Path to an RL model (Aurora).'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    # t = np.arange(0, 30, 0.1)
    # bw = np.ones_like(t) * 0.6

    # bw[10:20] = 0.1

    if args.trace:
        trace = Trace.load_from_file(args.trace)
    else:
        trace = generate_trace(duration_range=(30, 30),
                               bandwidth_lower_bound_range=(0.02, 0.02),
                               bandwidth_upper_bound_range=(0.6, 0.6),
                               delay_range=(25, 25),
                               loss_rate_range=(0.0, 0.0),
                               queue_size_range=(20, 20),
                               T_s_range=(10, 10),
                               delay_noise_range=(0, 0), seed=42)

    # trace.bandwidths = bw
    # trace.timestamps = t
    # trace.queue_size = 20
    # print(trace.queue_size)

    # trace = generate_trace(duration_range=(30, 30),
    #                        bandwidth_lower_bound_range=(1, 1),
    #                        bandwidth_upper_bound_range=(1, 1),
    #                        delay_range=(25, 25),
    #                        loss_rate_range=(0.0, 0.0),
    #                        queue_size_range=(20, 20),
    #                        T_s_range=(10, 10),
    #                        delay_noise_range=(0, 0), seed=42)

    simulator = Simulator(
        trace, args.save_dir, args.cc, args.app,
        model_path=args.model, lookup_table_path=args.lookup_table)
    # lookup_table_path = "/home/zxxia/PhD/Projects/net-rl/AE_lookup_table/segment_3IY83M-m6is_480x360.mp4.csv"
    # model_path="/home/zxxia/PhD/Projects/net-rl/models/cc/pretrained/pretrained.ckpt"
    # model_path = "/home/zxxia/PhD/Projects/net-rl/models/cc/udr2/udr2_seed_10/seed_1/model_step_784800.ckpt"

    # simulator = Simulator(
    #     trace, "results/optimal_rl_0.1", 'aurora', "video_streaming",
    #     model_path=model_path, lookup_table_path=lookup_table_path)
    # simulator = Simulator(
    #     trace, "results/const_rl_0.1", '', "video_streaming",
    #     model_path=model_path, lookup_table_path=lookup_table_path)
    # simulator = Simulator(
    #     trace, "results", 'aurora', "file_transfer", model_path=model_path)
    # simulator = Simulator(trace, "results", '', "file_transfer")
    # simulator = Simulator(trace, "results", '', "video_streaming", lookup_table_path=lookup_table_path)
    # simulator = Simulator(trace, "results/gcc", 'gcc', "video_streaming", lookup_table_path=lookup_table_path)
    # simulator.sender.pacer.set_pacing_rate_mbps(1.2)
    # simulator = Simulator(
    #     trace, "results", 'aurora', "video_streaming", model_path=model_path, lookup_table_path=lookup_table_path)
    # simulator = Simulator(
    #     trace, "results/bbr", 'bbr', "file_transfer")
    # simulator.simulate(35)

    # from simulator_new.trace import generate_trace
    # trace = generate_trace(duration_range=(30, 30),
    #                        bandwidth_lower_bound_range=(1.2, 1.2),
    #                        bandwidth_upper_bound_range=(1.2, 1.2),
    #                        delay_range=(25, 25),
    #                        loss_rate_range=(0.1, 0.1),
    #                        queue_size_range=(10, 10),
    #                        T_s_range=(0, 0),
    #                        delay_noise_range=(0, 0))
    # scheduler = UDRTrainScheduler("", [trace], 1.0)

    # train_aurora(scheduler, "", 72000, 10, "results/train", 7200)


    # simulator = Simulator(
    #     trace, "results/exp", '', "video_streaming", lookup_table_path=lookup_table_path)
    # simulator.sender.set_pacing_rate_mbps(0.3)
    simulator.simulate(int(trace.duration))

if __name__ == "__main__":
    t_start = time.time()
    main()
    print("time used: {:.2f}s".format(time.time() - t_start))
