import os
from math import floor
import shutil
from argparse import ArgumentParser
from pathlib import Path

from bs4 import BeautifulSoup
from owlready2 import Ontology, destroy_entity

from vr_neem_converter.utils import load_ontology


def hand_participates_in_contact(contact_indi, semantic_map: Ontology):
    right_hand_class = semantic_map.search(iri="http://knowrob.org/kb/knowrob.owl#GenesisRightHand")[0]
    left_hand_class = semantic_map.search(iri="http://knowrob.org/kb/knowrob.owl#GenesisLeftHand")[0]
    return thing_participates_in_contact(contact_indi, right_hand_class) or thing_participates_in_contact(contact_indi,
                                                                                                          left_hand_class)


def floor_participates_in_contact(contact_indi, semantic_map: Ontology):
    floor_class = semantic_map.search(iri="http://knowrob.org/kb/knowrob.owl#IAIFloor")[0]
    return thing_participates_in_contact(contact_indi, floor_class)


def thing_participates_in_contact(contact_indi, thing_class):
    for contact_obj in contact_indi.inContact:
        # if thing_class.iri in [cls.iri for cls in contact_obj.is_a]:
        if thing_class in contact_obj.is_a:
            return True
    return False


def filter_hand_touching_floor(onto: Ontology, html: str, semantic_map: Ontology) -> str:
    """
    Modifies onto in place and returns a new HTML string for the episode timeline
    """
    # Remove individuals from the ontology
    touching_class = onto.search(iri='http://knowrob.org/kb/knowrob.owl#TouchingSituation')[0]
    indis_to_remove = []
    for indi in onto.individuals():
        if touching_class in indi.is_a:
            if hand_participates_in_contact(indi, semantic_map) and floor_participates_in_contact(indi, semantic_map):
                indis_to_remove.append(indi)
    if len(indis_to_remove) > 0:
        print("Removing individuals!")
    for indi in indis_to_remove:
        destroy_entity(indi)

    # Remove the same individuals from the html timeline
    cleaned_html = []
    for line in html.splitlines():
        remove_line = any([indi.name in line for indi in indis_to_remove])
        if not remove_line:
            cleaned_html.append(line)
        else:
            print(f"Removing line: {line}")
    return "\n".join(cleaned_html)


def main(args):
    if args.output_dir_cleaned_vr_demos.exists():
        shutil.rmtree(args.output_dir_cleaned_vr_demos.as_posix())
    shutil.copytree(args.input_dir_vr_demos.as_posix(), args.output_dir_cleaned_vr_demos.as_posix())
    semantic_map_path = next(args.output_dir_cleaned_vr_demos.glob("**/*_SM.owl"))
    semantic_map = load_ontology(semantic_map_path)
    for episode_data_path in args.output_dir_cleaned_vr_demos.glob("**/*_ED.owl"):
        # Load ontology & html
        onto = load_ontology(episode_data_path.as_posix())
        html_path = episode_data_path.as_posix()[:-6] + "TL.html"
        if not os.path.exists(html_path):
            continue    # For some reason, SC2_HD_4 does not have a timeline
        with open(html_path) as html_file:
            html = html_file.read()

        # Clean ontology & html
        html = filter_hand_touching_floor(onto, html, semantic_map)

        # Save ontology & HTML
        onto.save(episode_data_path.as_posix())
        with open(html_path, "w") as html_file:
            html_file.write(html)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("input_dir_vr_demos", type=Path,
                        help="Path to dir containing VR demonstrations ('dump' and 'SemLog' subdirs)")
    parser.add_argument("output_dir_cleaned_vr_demos", type=Path)
    main(parser.parse_args())
