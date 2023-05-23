import tempfile
from typing import List, Tuple

from knowrob_industrial.utils import resolve_package_urls
from neem_interface_python.neem_interface import NEEMInterface
from neem_interface_python.rosprolog_client import atom
from owlready2 import get_ontology, Ontology, ThingClass


def pose_to_knowrob_string(pose: List[float], reference_frame="world") -> str:
    """
    Convert a pq list [x,y,z,qx,qy,qz,qw] to a KnowRob pose "[reference_cs, [x,y,z],[qx,qy,qz,qw]]"
    """
    return f"[{atom(reference_frame)}, [{pose[0]},{pose[1]},{pose[2]}], [{pose[3]},{pose[4]},{pose[5]},{pose[6]}]]"


def assert_agent_and_hand(semantic_map: Ontology, neem_interface: NEEMInterface, agent_iri: str,
                          end_effector_class: ThingClass) -> str:
    """
    Assert meta-information about the hands (e.g. fingers etc.) of the VR avatar
    Assumption: All objects in the semantic map have already been asserted into the knowledge base
    """
    # Hand
    hand_indi = semantic_map.search_one(type=end_effector_class)
    agent_iri = neem_interface.assert_agent_with_effector(hand_indi.iri, agent_iri=agent_iri)

    # Fingertips
    thumb_class = semantic_map.search_one(iri="*rThumb3")
    thumb_indi = semantic_map.search_one(type=thumb_class)
    neem_interface.prolog.ensure_once(
        f"kb_project(holds({atom(hand_indi.iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasFinger', {atom(thumb_indi.iri)}))")
    index_class = semantic_map.search_one(iri="*rIndex3")
    index_indi = semantic_map.search_one(type=index_class)
    neem_interface.prolog.ensure_once(
        f"kb_project(holds({atom(hand_indi.iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasFinger', {atom(index_indi.iri)}))")

    return agent_iri


def load_ontology(owl_filepath: str) -> Ontology:
    temp_file = tempfile.NamedTemporaryFile(suffix='.owl', mode="w+t")
    with open(owl_filepath) as owl_file:
        patched_owl = resolve_package_urls(owl_file.read())
        temp_file.write(patched_owl)
    return get_ontology(f"file://{temp_file.name}").load()


def get_initial_situations(neem_interface: NEEMInterface, action_start_time: float, time_padding=0.0) -> List[str]:
    start_time = action_start_time - time_padding
    try:
        res = neem_interface.prolog.ensure_all_solutions(f"""is_state(State), has_time_interval(State, StartTime, EndTime),
            StartTime =< {start_time}, EndTime > {start_time}, holds(Situation, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', State)""")
        return [sol["Situation"] for sol in res]
    except:
        return []


def get_terminal_situations(neem_interface: NEEMInterface, action_end_time: float, time_padding=0.2) -> List[str]:
    end_time = action_end_time + time_padding
    try:
        res = neem_interface.prolog.ensure_all_solutions(f"""is_state(State), has_time_interval(State, StartTime, EndTime),
            StartTime =< {end_time}, EndTime > {end_time}, holds(Situation, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', State)""")
        return [sol["Situation"] for sol in res]
    except:
        return []


def get_runtime_situations(neem_interface: NEEMInterface, action_start_time: float, action_end_time: float) -> List[str]:
    try:
        res = neem_interface.prolog.ensure_all_solutions(f"""is_state(State), has_time_interval(State, StartTime, EndTime),
            StartTime =< {action_start_time}, EndTime >= {action_end_time}, holds(Situation, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', State)""")
        return [sol["Situation"] for sol in res]
    except:
        return []
