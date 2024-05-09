import argparse
import time

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
        '--ae-guided',
        action="store_true",
        help="AE guide reward if specified.",
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

    if args.trace:
        trace = Trace.load_from_file(args.trace)
    else:
        trace = generate_trace(duration_range=(30, 30),
                               bandwidth_lower_bound_range=(1, 1),
                               bandwidth_upper_bound_range=(5, 5),
                               delay_range=(25, 25),
                               loss_rate_range=(0.0, 0.0),
                               queue_size_range=(20, 20),
                               T_s_range=(10, 10),
                               delay_noise_range=(0, 0), seed=42)

    simulator = Simulator(
        trace, args.save_dir, args.cc, args.app,
        model_path=args.model, lookup_table_path=args.lookup_table,
        ae_guided=args.ae_guided)
    simulator.simulate(int(trace.duration))

if __name__ == "__main__":
    t_start = time.time()
    main()
    print("time used: {:.2f}s".format(time.time() - t_start))
