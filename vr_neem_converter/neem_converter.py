"""
Copyright (C) 2021 ArtiMinds Robotics GmbH
"""
import os
import shutil
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Tuple, List

from tqdm import tqdm
from neem_interface_python.neem_interface import NEEMInterface, Episode
from neem_interface_python.rosprolog_client import atom
from neem_interface_python.utils.utils import Datapoint
from owlready2 import Ontology
from pymongo import MongoClient
from pymongo.collection import Collection

from event_converters import EventConverter
from vr_neem_converter.utils import load_ontology, assert_agent_and_hand, get_initial_situations, \
    get_terminal_situations, get_runtime_situations


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
        self.all_objects = {}  # Maps object IRI to type
        self.active_objects = {}  # Maps object IRI to type for objects involved in interactions with other objects
        self.episode = None

    def convert(self, neem_output_path, episode_name: str = None):
        db_name = os.listdir(os.path.join(self.vr_neem_dir, "dump"))[0]
        os.system(f"mongorestore {os.path.join(self.vr_neem_dir, 'dump')}")
        db = self.mongo_client[db_name]

        all_event_owl_filepaths = list(Path(os.path.join(self.vr_neem_dir, "SemLog", "Episodes")).glob("**/*_ED.owl"))
        for collection_name in db.list_collection_names():
            if collection_name.endswith(".meta"):
                continue
            if episode_name is not None and episode_name not in collection_name:
                continue
            documents = list(db[collection_name].find({}))
            if len(documents) == 0:
                continue

            start_time = time.time()
            episode_output_dir = os.path.join(neem_output_path, collection_name)
            if os.path.exists(episode_output_dir):
                shutil.rmtree(episode_output_dir)
            os.makedirs(episode_output_dir)

            semantic_map_dir = os.path.join(self.vr_neem_dir, "SemLog", "SemanticMap")
            semantic_map_owl_filename = next(filter(lambda fn: fn.endswith("SM.owl"), os.listdir(semantic_map_dir)))
            semantic_map_owl_filepath = os.path.join(semantic_map_dir, semantic_map_owl_filename)
            # Create new episode and make assertions
            with Episode(self.neem_interface, "http://www.artiminds.com/kb/artm.owl#PickAndPlaceTask",
                         self.env_owl,
                         self.env_indi_name,
                         self.env_urdf, self.agent_owl, self.agent, self.agent_urdf,
                         episode_output_dir) as self.episode:
                event_owl_filepath = list(filter(lambda fp: collection_name in str(fp), all_event_owl_filepaths))[0]
                self.agent, self.all_objects, self.active_objects = self._assert_objects_and_agent(
                    semantic_map_owl_filepath, event_owl_filepath.as_posix())
                self._assert_events(event_owl_filepath.as_posix())
                self._assert_tf(db[collection_name])
            print(f"Conversion took {time.time() - start_time:.4f} seconds")

    def _assert_objects_and_agent(self, semantic_map_owl_filepath: str, event_owl_filepath: str) -> Tuple[
        str, dict, dict]:
        semantic_map = load_ontology(semantic_map_owl_filepath)
        print(f"Loading {event_owl_filepath}")
        event_ontology = load_ontology(event_owl_filepath)
        known_classes = [x["Class"] for x in self.neem_interface.prolog.all_solutions("is_class(Class)")]
        objects = {}
        active_objects = {}

        # Assert objects of known types as individuals of that type, else just as dul:'PhysicalObject'
        all_individuals = list(semantic_map.individuals())
        print(f"Asserting object types for {len(all_individuals)} individuals...")
        for obj_indi in tqdm(semantic_map.individuals()):
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
                self.neem_interface.prolog.ensure_once(f"""
                    kb_project([
                        has_participant({atom(obj_indi.iri)}, {atom(self.episode.top_level_action_iri)}) 
                    ])
                """)
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
        object_iris = {fully_qualified_name.split("#")[-1]: fully_qualified_name for fully_qualified_name in
                       self.active_objects.keys()}

        # Also prepare the IRIs of the hand and fingers I care about
        fully_qualified_hand_iri = next(
            iri for iri, obj_class in self.all_objects.items() if obj_class == self.end_effector_class_name)
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
                    Datapoint.from_unreal(ts, fully_qualified_name, "world", obj["pose"][:3],
                                          obj["pose"][3:]))

            # 'skel_individuals' are the 2 hands
            for hand in document["skel_individuals"]:
                try:
                    hand_id = object_iris[hand["id"]]
                    if hand_id != fully_qualified_hand_iri:  # Don't care about other hand
                        continue
                except KeyError:  # Other hand was not in active objects
                    continue

                # TF of the hand itself
                datapoints.append(
                    Datapoint.from_unreal(ts, hand_id, "world", hand["pose"][:3], hand["pose"][3:]))

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
                        Datapoint.from_unreal(ts, bone_id, "world", bone["pose"][:3], bone["pose"][3:]))
        self.neem_interface.assert_tf_trajectory(datapoints)

    def _assert_events(self, owl_filepath: str):
        """
        Assert states and actions into KnowRob.
        :param owl_filepath: Path to OWL file containing event data, e.g. testing/resources/episode_1/set_table_events.owl
        """
        onto = load_ontology(owl_filepath)
        event_individuals = set(onto.individuals()).intersection(onto.search(inEpisode="*"))
        print(f"Asserting state/situation transitions for {len(event_individuals)} event individuals")
        event_converter = EventConverter(self)
        event_times = self._assert_states(event_converter, event_individuals)
        action_times = self._assert_known_actions(event_converter, event_individuals, event_times)
        event_times = list(set(event_times))    # deduplicate
        event_times.sort()
        all_actions = self._assert_anonymous_actions(event_converter, action_times, event_times)
        print(f"NEEM has {len(all_actions)} actions")
        self._assert_situation_transition_and_situations_for_actions(all_actions)

    def _assert_states(self, event_converter, event_individuals) -> List[float]:
        """
        Assert the state timeline into KnowRob.
        State semantics (see EventConverter):
            * A State is a durative Event (it has a time interval)
            * Multiple Situations may manifestIn a State
            * If a Situation manifestsIn a State, it holds for the entire duration of the State
        """
        event_times = []
        # States; each state also has one corresponding Situation with relations and role bindings
        for event_individual in filter(lambda event_indi: event_converter.is_state(event_indi), event_individuals):
            state_iri = event_converter.convert(event_individual)
            res = self.neem_interface.prolog.ensure_once(
                f"kb_call(has_time_interval({atom(state_iri)}, StartTime, EndTime))")
            event_times.append(float(res["StartTime"]))
            event_times.append(float(res["EndTime"]))
        return event_times

    def _assert_known_actions(self, event_converter, event_individuals, event_times) -> dict:
        """
        Assert the action timeline into Knowrob. This only takes into account the actions which have been provided by USemLog.
        Action semantics (see EventConverter):
            * An Action is a durative Event (it has a time interval)
            * Multiple Situations may manifestIn an Action
            * If a Situation manifestsIn an Action, it holds for the entire duration of the Action
            * Multiple SituationTransitions may manifestIn an Action
                * Their initialSituations is the Set of Situations which manifestIn States overlapping (exclusive) with the beginning of the Action;
                  their terminalSituations is the Set of Situations which manifestIn States overlapping (exclusive) with the end of the Action
        """
        action_times = {}
        for event_individual in filter(lambda event_indi: event_converter.is_action(event_indi), event_individuals):
            try:
                action_iri = event_converter.convert(event_individual)
                res = self.neem_interface.prolog.ensure_once(
                    f"kb_call(has_time_interval({atom(action_iri)}, StartTime, EndTime))")
                action_times[action_iri] = {"start_time": float(res["StartTime"]),
                                            "end_time": float(res["EndTime"])}
                event_times.append(float(res["StartTime"]))
                event_times.append(float(res["EndTime"]))
            except NotImplementedError:
                continue    # Anonymous actions will be asserted for all gaps in the timeline
        return action_times

    def _assert_anonymous_actions(self, event_converter, action_times, event_times) -> List[str]:
        """
        Assert new "anonymous" actions (instances of PhysicalAction) between state transitions which don't have actions yet.
        This enforces the rule that there can't be "gaps" in the timeline - because we don't exactly know at what precise moment actions
        begin or end, we make sure that "some action" is always occurring, and that "some other action" occurs when there is a state transition.
        """
        all_actions = []
        # Anonymous actions for force-dynamic events which don't have actions
        for i in range(len(event_times) - 1):
            start_time = event_times[i]
            end_time = event_times[i + 1]
            have_action_during_interval = False
            for action_iri, action_time_dict in action_times.items():
                if action_time_dict["start_time"] <= start_time and action_time_dict["end_time"] >= end_time:
                    have_action_during_interval = True
                    all_actions.append(action_iri)
                    break
            if have_action_during_interval:
                continue
            # There is a gap in the timeline --> create anonymous action
            action_iri = event_converter.create_anonymous_action(start_time, end_time)
            all_actions.append(action_iri)
            print(f"Created anonymous action: {action_iri} ({start_time} -> {end_time})")
        return all_actions

    def _assert_situation_transition_and_situations_for_actions(self, actions: List[str]):
        """
        Each action has a Situation transition
            * which has N initialSituations, which manifest at start time
            * which has M terminalSituations, which manifest at end time
        Each action also has the situations of the states with which it (fully) overlaps
        """
        for action_iri in actions:
            res = self.neem_interface.prolog.ensure_once(
                f"kb_call(has_time_interval({atom(action_iri)}, StartTime, EndTime))")
            start_time = float(res["StartTime"])
            end_time = float(res["EndTime"])
            situations_initial = get_initial_situations(self.neem_interface, start_time)
            situations_terminal = get_terminal_situations(self.neem_interface, end_time)
            situations_runtime = get_runtime_situations(self.neem_interface, start_time, end_time)
            situation_transition_iri = self.neem_interface.assert_situation(self.agent, [],
                                                                            'http://www.ease-crc.org/ont/SOMA.owl#SituationTransition')
            self.neem_interface.prolog.ensure_once(
                f"kb_project(holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(action_iri)}))")
            for situation in situations_initial:
                self.neem_interface.prolog.ensure_once(
                    f"kb_project(holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasInitialSituation', {atom(situation)}))")
            for situation in situations_terminal:
                self.neem_interface.prolog.ensure_once(
                    f"kb_project(holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasTerminalSituation', {atom(situation)}))")
            for situation in situations_runtime:
                self.neem_interface.prolog.ensure_once(
                    f"kb_project(holds({atom(situation)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(action_iri)}))")

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
                                     env_indi_name="http://knowrob.org/kb/supermarket.owl#Supermarket_VR_0",
                                     env_urdf="/home/lab019/alt/catkin_ws/src/ilias/ilias_final_experiments/urdf/dm_room_vr.urdf",
                                     env_urdf_prefix="http://knowrob.org/kb/supermarket.owl#",
                                     end_effector_class_name="http://knowrob.org/kb/knowrob.owl#GenesisRightHand")
    neem_converter.convert(args.output_dir, args.episode_name)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("vr_neem_dir", type=str)
    parser.add_argument("output_dir", type=str)
    parser.add_argument("--episode_name", type=str)
    main(parser.parse_args())
