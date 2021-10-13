"""
Copyright (C) 2021 ArtiMinds Robotics GmbH
"""
from typing import Tuple, List

from neem_interface_python.neem_interface import NEEMInterface, Episode
from neem_interface_python.rosprolog_client import atom


class EventConverter:
    def __init__(self, parent):
        self.parent = parent
        self.asserted_states = []

        self.evt_converters = {
            "GraspingSomething": self.convert_grasping_something,
            "SlicingSomething": self.convert_slicing_something,
            "TouchingSituation": self.convert_touching_situation,
            "SupportedBySituation": self.convert_supported_by_situation,
            "ContainerManipulation": self.convert_container_manipulation,
            "PickUpSituation": self.convert_pick_up_situation,
            "PreGraspSituation": self.convert_pregrasp_situation,
            "PutDownSituation": self.convert_put_down_situation,
            "ReachingForSomething": self.convert_reaching_situation,
            "SlidingSituation": self.convert_sliding_situation,
            "TransportingSituation": self.convert_transporting_situation
        }

    def _extract_timestamp(self, timepoint_indi):
        indi_name = timepoint_indi.name
        return float(indi_name.split("_")[-1])

    def convert(self, event_indi):
        event_class = event_indi.is_a[0]
        return self.evt_converters[event_class.name](event_indi)

    @staticmethod
    def is_state(event_indi) -> bool:
        return event_indi.is_a[0].name in ["TouchingSituation", "SupportedBySituation", "GraspingSomething"]

    @staticmethod
    def is_action(event_indi) -> bool:
        return not EventConverter.is_state(event_indi)

    def convert_grasping_something(self, indi):
        """
        Grasping is a STATE, called "Grasp" in the HTML viz, called "GraspState" in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        gripper = indi.performedBy[0].iri     # TODO: Assert gripper and graspedObject as Roles
        graspedObject = indi.objectActedOn[0].iri
        state_iri = self.parent.neem_interface.assert_state([gripper, graspedObject], start_time, end_time,
                                                             state_type="soma:'GraspState'")
        self.asserted_states.append(state_iri)

    def convert_slicing_something(self, indi):
        # raise NotImplementedError()
        pass

    def convert_touching_situation(self, indi):
        """
        TouchingSituation is a  STATE, called "Contact" in the HTML viz, called "ContactState" in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        participants = [thing.iri for thing in indi.inContact]
        state_iri = self.parent.neem_interface.assert_state(participants, start_time, end_time,
                                                            state_type="soma:'ContactState'")
        self.asserted_states.append(state_iri)

    def convert_supported_by_situation(self, indi):
        """
        SupportedBy is a STATE, called "SupportedBy" in the HTML viz, called "SupportState" in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        supportee = indi.isSupported[0].iri     # TODO: Assert supporter and supportee as Roles
        supporter = indi.isSupported[0].iri
        state_iri = self.parent.neem_interface.assert_state([supportee, supporter], start_time, end_time,
                                                            state_type="soma:'SupportState'")
        self.asserted_states.append(state_iri)

    def convert_container_manipulation(self, indi):
        # raise NotImplementedError()
        pass

    def convert_pick_up_situation(self, indi):
        """
        PickUp is an ACTION
        """
        # raise NotImplementedError()
        pass

    def convert_pregrasp_situation(self, indi):
        """
        PreGrasp is an ACTION, called "PreGrasp" in the HTML viz, mapped to a PhysicalAction for a task artm:PreGraspTask in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        actor = indi.performedBy[0].iri
        obj = indi.objectActedOn[0].iri
        action_iri = self.parent.neem_interface.add_subaction_with_task(self.parent.episode.top_level_action_iri,
                                                                        sub_action_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalAction",
                                                                        task_type="http://www.artiminds.com/kb/artm.owl#PreGraspTask",
                                                                        start_time=start_time, end_time=end_time)
        initial_situation = self._assert_situation_manifesting_at_timestamp(start_time, actor, [obj])
        terminal_situation = self._assert_situation_manifesting_at_timestamp(end_time, actor, [obj])
        situation_transition = self._assert_situation_transition_for_action(action_iri, initial_situation,
                                                                            terminal_situation)

    def convert_put_down_situation(self, indi):
        # raise NotImplementedError()
        pass

    def convert_reaching_situation(self, indi):
        """
        Reaching is an ACTION, called "Reach" in the HTML viz, mapped to a PhysicalAction for task Reaching in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        actor = indi.performedBy[0].iri
        obj = indi.objectActedOn[0].iri
        action_iri = self.parent.neem_interface.add_subaction_with_task(self.parent.episode.top_level_action_iri,
                                                                        sub_action_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalAction",
                                                                        task_type="http://www.ease-crc.org/ont/SOMA.owl#Reaching",
                                                                        start_time=start_time, end_time=end_time)
        initial_situation = self._assert_situation_manifesting_at_timestamp(start_time, actor, [obj])
        terminal_situation = self._assert_situation_manifesting_at_timestamp(end_time, actor, [obj])
        situation_transition = self._assert_situation_transition_for_action(action_iri, initial_situation, terminal_situation)

    def convert_sliding_situation(self, indi):
        # raise NotImplementedError()
        pass

    def convert_transporting_situation(self, indi):
        # raise NotImplementedError()
        pass

    def _convert_common(self, indi):
        """
        Each event corresponds to an Action
        :param indi:
        :return:
        """
        pass

    def _assert_situation_manifesting_at_timestamp(self, start_time: float, agent: str, objects: List[str]) -> str:
        situation_iri = self.parent.neem_interface.assert_situation(agent, objects, "dul:'Situation'")
        for state_iri in self.asserted_states:
            res = self.parent.neem_interface.prolog.once(
                f"kb_call(has_time_interval({atom(state_iri)}, StartTime, EndTime))")
            state_start_time = float(res["StartTime"])
            state_end_time = float(res["EndTime"])
            if state_start_time < start_time < state_end_time:
                self.parent.neem_interface.prolog.once(
                    f"kb_project(holds({atom(situation_iri)}, soma:'manifestsIn', {atom(state_iri)}))")
        return situation_iri

    def _assert_situation_transition_for_action(self, action_iri: str, initial_situation: str, terminal_situation: str) -> str:
        agent = self.parent.neem_interface.prolog.once(f"kb_call(is_performed_by({atom(action_iri)}, Agent))")["Agent"]
        situation_transition_iri = self.parent.neem_interface.assert_situation(agent, [], "soma:'SituationTransition'")
        self.parent.neem_interface.prolog.once(f"""
            kb_project([
                holds({atom(situation_transition_iri)}, "soma:'hasInitialSituation'", {atom(initial_situation)}),
                holds({atom(situation_transition_iri)}, "soma:'hasTerminalSituation'", {atom(terminal_situation)}),
                holds({atom(situation_transition_iri)}, "soma:'manifestsIn'", {atom(action_iri)})
            ])
        """)
        return situation_transition_iri
