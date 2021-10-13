"""
Copyright (C) 2021 ArtiMinds Robotics GmbH
"""
import json
import os
from argparse import ArgumentParser

from neem_interface_python.neem_interface import NEEMInterface
from neem_interface_python.utils import Datapoint
from owlready2 import get_ontology, onto_path


class VRNEEMConverter:
    def __init__(self, vr_neem_dir: str):
        self.neem_interface = NEEMInterface()
        self.vr_neem_dir = vr_neem_dir

    def convert(self):
        tf_json_filename = next(filter(lambda fn: fn.endswith("_tf.json"), os.listdir(self.vr_neem_dir)))
        events_owl_filename = next(filter(lambda fn: fn.endswith("_events.owl"), os.listdir(self.vr_neem_dir)))
        self._write_tf(os.path.join(self.vr_neem_dir, tf_json_filename))
        self._assert_events(os.path.join(self.vr_neem_dir, events_owl_filename))

    def _write_tf(self, tf_json_filepath: str):
        """
        Assert TF data into KnowRob
        :param tf_json_filepath: Path to JSON file containing TF data, e.g. testing/resources/episode_1/set_table_1_tf.json
        """
        with open(tf_json_filepath) as tf_json_file:
            tf_data = json.load(tf_json_file)
        datapoints = [Datapoint.from_tf(tf_msg) for tf_msg in tf_data]
        self.neem_interface.assert_tf_trajectory(datapoints)

    def _assert_events(self, owl_filepath: str):
        """
        Assert the events as subactions with state transitions into KnowRob
        :param owl_filepath: Path to OWL file containing event data, e.g. testing/resources/episode_1/set_table_events.owl
        """
        onto = get_ontology(f"file://{owl_filepath}").load()


if __name__ == '__main__':
    # parser = ArgumentParser()
    # parser.add_argument("vr_neem_dir")
    owl_filepath = "/home/lab019/alt/vr-neem-converter/testing/resources/episode_1/set_table_events.owl"
    onto = get_ontology(f"file://{owl_filepath}").load()
    print("Done")



