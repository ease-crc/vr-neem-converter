import json
from argparse import ArgumentParser

from scipy.spatial.transform import Rotation


def main(args):
    pos_cm = [args.x, args.y, args.z]
    pos_m = [p / 100.0 for p in pos_cm]
    pos_rhs = [pos_m[1], pos_m[0], pos_m[2]]
    ori_rhs = [-args.qx, args.qy, -args.qz, args.qw]
    print(pos_rhs + ori_rhs)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("x", type=float)
    parser.add_argument("y", type=float)
    parser.add_argument("z", type=float)
    parser.add_argument("qx", type=float)
    parser.add_argument("qy", type=float)
    parser.add_argument("qz", type=float)
    parser.add_argument("qw", type=float)
    main(parser.parse_args())