import os
from argparse import ArgumentParser
from typing import List

import numpy as np
from neem_interface_python.neem import NEEM
from neem_interface_python.rosprolog_client import atom
from neem_utils.knowrob_queries import parse_tf_traj
from pymongo import MongoClient
import matplotlib.pyplot as plt


class NEEMPlotter:
    def __init__(self, neem: NEEM):
        self.neem = neem

    def plot_tf(self, hand_iri: str, index_iri: str, thumb_iri: str, other_objects: List[str]):
        objects = [hand_iri, index_iri, thumb_iri] + other_objects
        fig, axes = plt.subplots(4, 1)

        res = self.neem.prolog.ensure_all_solutions(f"""
            kb_call(instance_of(Event,dul:'Event'))
        """)
        events = [x["Event"] for x in res]
        start_time = np.inf
        end_time = -np.inf
        for event in events:
            res = self.neem.prolog.ensure_once(f"""
                kb_call(has_time_interval({atom(event)}, StartTime, EndTime))
            """)
            event_start_time = float(res["StartTime"])
            event_end_time = float(res["EndTime"])
            start_time = min(start_time, event_start_time)
            end_time = max(end_time, event_end_time)

        object_trajs = {object_iri: parse_tf_traj(self.neem.neem_interface.get_tf_trajectory(object_iri, start_time, end_time))
                        for object_iri in objects}

        # Object positions
        for object_iri, object_traj in object_trajs.items():
            if len(object_traj) == 0:
                continue
            first_pos = object_traj[0].pos
            first_ori = object_traj[0].ori.as_quat()
            print(f"Object {object_iri}: {first_pos[0]:.4f} {first_pos[1]:.4f} {first_pos[2]:.4f} {first_ori[0]:.4f} {first_ori[1]:.4f} {first_ori[2]:.4f} {first_ori[3]:.4f}")
            timestamps = [dp.timestamp for dp in object_traj]
            for dim in range(3):
                data = [dp.pos[dim] for dp in object_traj]
                axes[dim].plot(timestamps, data)

        # Gripper opening
        gripper_openings = []
        gripper_timestamps = []
        thumb_traj = object_trajs[thumb_iri]
        index_traj = object_trajs[index_iri]
        for i in range(len(thumb_traj)):
            gripper_openings.append(np.linalg.norm(np.array(thumb_traj[i].pos) - np.array(index_traj[i].pos)))
            gripper_timestamps.append(thumb_traj[i].timestamp)
        axes[3].plot(gripper_timestamps, gripper_openings)

        fig.legend(labels=[object_iri for object_iri in object_trajs.keys()])
        plt.show()


def main(args):
    plotter = NEEMPlotter(NEEM.load(args.neem_path))
    plotter.plot_tf(index_iri="http://knowrob.org/kb/ameva_log.owl#_hbZuZHsuk6Nqw-a8JyK4w",  # Index finger
                    thumb_iri="http://knowrob.org/kb/ameva_log.owl#jioI4tGSAkad0W91pTKUrw",  # Thumb
                    hand_iri="http://knowrob.org/kb/ameva_log.owl#BENamAV8rkibLIBc8asHhQ",   # Hand
                    other_objects=["http://knowrob.org/kb/ameva_log.owl#xV-vxMHrR0GJBOzkrti7FA",    # HangingDummy
                                   "http://knowrob.org/kb/ameva_log.owl#VAyxpxfxpU-6w0a_2WHSSA",    # ShelfSystem
                                   "http://knowrob.org/kb/ameva_log.owl#9jDlRIK1sU6wHIWg2FR13w",    # MountingBar
                                   "http://knowrob.org/kb/ameva_log.owl#tMwn8o6kC0aDQZSrcgRqwQ"     # MountingBar
                                   ])


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("neem_path", type=str)
    main(parser.parse_args())
