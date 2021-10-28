"""
Copyright (C) 2021 ArtiMinds Robotics GmbH
"""
import os
import shutil
from argparse import ArgumentParser
from typing import Tuple

from neem_interface_python.neem_interface import NEEMInterface, Episode
from neem_interface_python.rosprolog_client import atom
from neem_interface_python.utils import Datapoint
from owlready2 import Ontology
from pymongo import MongoClient
from pymongo.collection import Collection
from scipy.spatial.transform import Rotation
from event_converters import EventConverter
from vr_neem_converter.utils import load_ontology, assert_agent_and_hand


class VRNEEMConverter:
    def __init__(self, vr_neem_dir: str,
                 agent_owl="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/owl/vr_agent.owl",
                 agent_indi_name="http://knowrob.org/kb/vr_agent.owl#VRAgent_0",
                 agent_urdf="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/urdf/vr_agent.urdf",
                 env_owl="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/owl/supermarket.owl",
                 env_indi_name="http://knowrob.org/kb/supermarket.owl#Supermarket",
                 env_urdf="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/urdf/dm_room_vr.urdf",
                 env_urdf_prefix="http://knowrob.org/kb/supermarket.owl",
                 end_effector_class_name="http://knowrob.org/kb/knowrob.owl#GenesisRightHand"):
        self.neem_interface = NEEMInterface()
        self.vr_neem_dir = vr_neem_dir
        self.mongo_client = MongoClient()
        self.agent = agent_indi_name
        self.end_effector_class_name = end_effector_class_name
        self.agent_owl = agent_owl
        self.agent_urdf = agent_urdf
        self.env_owl = env_owl
        self.env_indi_name = env_indi_name
        self.env_urdf = env_urdf
        self.env_urdf_prefix = env_urdf_prefix
        self.all_objects = {}       # Maps object IRI to type
        self.active_objects = {}    # Maps object IRI to type for objects involved in interactions with other objects
        self.episode = None

    def convert(self, neem_output_path):
        db_name = os.listdir(os.path.join(self.vr_neem_dir, "dump"))[0]
        os.system(f"mongorestore {os.path.join(self.vr_neem_dir, 'dump')}")
        db = self.mongo_client[db_name]

        for collection_name in db.list_collection_names():
            if collection_name.endswith(".meta"):
                continue
            documents = list(db[collection_name].find({}))
            if len(documents) == 0:
                continue
            episode_output_dir = os.path.join(neem_output_path, collection_name)
            if os.path.exists(episode_output_dir):
                shutil.rmtree(episode_output_dir)
            os.makedirs(episode_output_dir)

            # Create new episode and make assertions
            with Episode(self.neem_interface, "http://www.artiminds.com/kb/artm.owl#PickAndPlaceTask", self.env_owl, self.env_indi_name,
                         self.env_urdf, self.env_urdf_prefix, self.agent_owl, self.agent, self.agent_urdf,
                         episode_output_dir) as self.episode:
                semantic_map_owl_filepath = os.path.join(self.vr_neem_dir, next(
                    filter(lambda fn: fn.endswith("SM.owl"), os.listdir(self.vr_neem_dir))))
                event_owl_filepath = os.path.join(self.vr_neem_dir, f"{collection_name}_ED.owl")
                self.agent, self.all_objects, self.active_objects = self._assert_objects_and_agent(semantic_map_owl_filepath, event_owl_filepath)
                self._assert_events(event_owl_filepath)
                self._assert_tf(db[collection_name])

            break   # TODO: Remove

    def _assert_objects_and_agent(self, semantic_map_owl_filepath: str, event_owl_filepath: str) -> Tuple[str, dict, dict]:
        semantic_map = load_ontology(semantic_map_owl_filepath)
        event_ontology = load_ontology(event_owl_filepath)
        known_classes = [x["Class"] for x in self.neem_interface.prolog.all_solutions("is_class(Class)")]
        objects = {}
        active_objects = {}

        # Assert objects of known types as individuals of that type, else just as dul:'PhysicalObject'
        for obj_indi in semantic_map.individuals():
            if obj_indi.is_a[0].iri in known_classes:
                obj_type = obj_indi.is_a[0].iri
            else:
                obj_type = "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#PhysicalObject"
            self.neem_interface.prolog.ensure_once(f"""
                kb_project([
                    is_individual({atom(obj_indi.iri)}), instance_of({atom(obj_indi.iri)}, {atom(obj_type)}) 
                ])
            """)
            objects[obj_indi.iri] = obj_type
            if self._is_active_object(obj_indi.iri, event_ontology):
                active_objects[obj_indi.iri] = obj_type

        # Assert hands as end effectors
        end_effector_class = semantic_map.search_one(iri=self.end_effector_class_name)
        agent_iri = assert_agent_and_hand(semantic_map, self.neem_interface, self.agent, end_effector_class)
        return agent_iri, objects, active_objects

    def _assert_tf(self, episode_coll: Collection):
        """
        Assert TF data into KnowRob
        """
        # Before starting, prepare a map of (short) object name to fully qualified object name
        # This is necessary because the MongoDB contains short names, but I want TF to contain fully qualified names
        object_iris = {fully_qualified_name.split("#")[-1] : fully_qualified_name for fully_qualified_name in self.active_objects.keys()}

        # Also prepare the IRIs of the hand and fingers I care about
        fully_qualified_hand_iri = next(iri for iri, obj_class in self.all_objects.items() if obj_class == self.end_effector_class_name)
        thumb_iri = next(iri for iri, obj_class in self.all_objects.items() if "rThumb" in obj_class)
        index_iri = next(iri for iri, obj_class in self.all_objects.items() if "rIndex" in obj_class)

        datapoints = []
        for document in episode_coll.find():
            ts = document["timestamp"]
            # 'individuals' are in world frame
            for obj in document["individuals"]:
                try:
                    fully_qualified_name = object_iris[obj["id"]]
                except KeyError:
                    # print(f"Cannot determine fully qualified IRI for {obj['id']}, skipping...")
                    continue
                # print(f"Writing TF for {obj['id']}")
                datapoints.append(
                    Datapoint.from_unreal(ts, fully_qualified_name, "world", obj["pose"][:3], Rotation.from_quat(obj["pose"][3:])))

            # 'skel_individuals' are the 2 hands
            for hand in document["skel_individuals"]:
                try:
                    hand_id = object_iris[hand["id"]]
                    if hand_id != fully_qualified_hand_iri:  # Don't care about other hand
                        continue
                except KeyError:    # Other hand was not in active objects
                    continue

                # TF of the hand itself
                datapoints.append(
                    Datapoint.from_unreal(ts, hand_id, "world", hand["pose"][:3], Rotation.from_quat(hand["pose"][3:])))

                # Just extract the fingers I care about
                # The hand has 20 bones: Thumb tip is 3, Index tip is 7
                for bone in hand["bones"]:
                    if bone["idx"] == 3:
                        bone_id = thumb_iri
                    elif bone["idx"] == 7:
                        bone_id = index_iri
                    else:
                        continue
                    datapoints.append(
                        Datapoint.from_unreal(ts, bone_id, "world", bone["pose"][:3], Rotation.from_quat(bone["pose"][3:])))
        self.neem_interface.assert_tf_trajectory(datapoints)

    def _assert_events(self, owl_filepath: str):
        """
        Assert the events as subactions with state transitions into KnowRob
        :param owl_filepath: Path to OWL file containing event data, e.g. testing/resources/episode_1/set_table_events.owl
        """
        onto = load_ontology(owl_filepath)
        event_individuals = onto.search(inEpisode="*")
        event_converter = EventConverter(self)
        for event_individual in filter(lambda event_indi: event_converter.is_state(event_indi), event_individuals):
            event_converter.convert(event_individual)
            if event_individual.name == "ESoDdqHPokacDoi5yhRweQ":
                break
        for event_individual in filter(lambda event_indi: event_converter.is_action(event_indi), event_individuals):
            event_converter.convert(event_individual)
            if event_individual.name == "KAAqauDdyUSR5O0SPmGtbQ":
                break

    def _is_active_object(self, obj_iri: str, event_ontology: Ontology) -> bool:
        """
        Return True if obj_iri is the object of any object property assertion in any event.
        Return False otherwise: The object does not take part in any event
        """
        for event_indi in filter(lambda indi: hasattr(indi, "startTime"), event_ontology.individuals()):
            for prop in event_indi.get_properties():
                for other_indi in prop[event_indi]:
                    if other_indi.iri == obj_iri:
                        return True
        return False


def main(args):
    neem_converter = VRNEEMConverter(args.vr_neem_dir,
                                     agent_owl="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/owl/vr_agent.owl",
                                     agent_indi_name="http://knowrob.org/kb/vr_agent.owl#VRAgent_0",
                                     agent_urdf="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/urdf/vr_agent.urdf",
                                     env_owl="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/owl/supermarket.owl",
                                     env_indi_name="http://knowrob.org/kb/supermarket.owl#Supermarket",
                                     env_urdf="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/urdf/dm_room_vr.urdf",
                                     env_urdf_prefix="http://knowrob.org/kb/supermarket.owl",
                                     end_effector_class_name="http://knowrob.org/kb/knowrob.owl#GenesisRightHand")
    neem_converter.convert(args.output_dir)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("vr_neem_dir", type=str)
    parser.add_argument("output_dir", type=str)
    main(parser.parse_args())
