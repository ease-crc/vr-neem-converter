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

    def convert_grasping_something(self, indi) -> str:
        """
        Grasping is a STATE, called "Grasp" in the HTML viz, called "GraspState" in SOMA
        Gripper and Graspee are related via http://www.artiminds.com/kb/knowrob_industrial.owl#GraspRelation
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        gripper = indi.performedBy[0].iri
        grasped_object = indi.objectActedOn[0].iri
        state_iri = self._assert_state([gripper, grasped_object], start_time, end_time,
                                       state_type='http://www.ease-crc.org/ont/SOMA.owl#GraspState')

        # Assert corresponding situation and role binding
        situation_iri = self._assert_situation_for_state(state_iri, [gripper, grasped_object])
        self.parent.neem_interface.prolog.ensure_once(f"""
            kb_project(object_grasped_in_situation({atom(grasped_object)}, {atom(gripper)}, {atom(situation_iri)})) 
        """)
        self.asserted_states.append(state_iri)
        return state_iri

    def convert_slicing_something(self, indi) -> str:
        # raise NotImplementedError()
        pass

    def convert_touching_situation(self, indi) -> str:
        """
        TouchingSituation is a  STATE, called "Contact" in the HTML viz, called "ContactState" in SOMA
        Objects in contact are related via http://www.artiminds.com/kb/knowrob_industrial.owl#ContactRelation
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        participants = [thing.iri for thing in indi.inContact]
        state_iri = self._assert_state(participants, start_time, end_time,
                                       state_type='http://www.ease-crc.org/ont/SOMA.owl#ContactState')

        # Assert corresponding situation and role binding
        situation_iri = self._assert_situation_for_state(state_iri, participants)
        self.parent.neem_interface.prolog.ensure_once(f"""
            kb_project(objects_touch_in_situation({atom(participants[0])}, {atom(participants[1])}, {atom(situation_iri)}))
        """)
        self.asserted_states.append(state_iri)
        return state_iri

    def convert_supported_by_situation(self, indi) -> str:
        """
        SupportedBy is a STATE, called "SupportedBy" in the HTML viz, called "SupportState" in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        supportee = indi.isSupported[0].iri
        supporter = indi.isSupporting[0].iri
        participants = [supportee, supporter]
        state_iri = self._assert_state(participants, start_time, end_time,
                                       state_type='http://www.ease-crc.org/ont/SOMA.owl#SupportState')

        # Assert corresponding situation and role binding
        situation_iri = self._assert_situation_for_state(state_iri, participants)
        self.parent.neem_interface.prolog.ensure_once(f"""
                kb_project(object_supported_in_situation({atom(supportee)}, {atom(supporter)}, {atom(situation_iri)}))
            """)
        self.asserted_states.append(state_iri)
        return state_iri

    def convert_container_manipulation(self, indi) -> str:
        # raise NotImplementedError()
        pass

    def convert_pick_up_situation(self, indi) -> str:
        """
        PickUp is an ACTION, called PickUp in the HTML viz, mapped to a PhysicalAction for a task soma:PickingUp in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        actor = indi.performedBy[0].iri
        obj = indi.objectActedOn[0].iri
        action_iri = self.parent.neem_interface.add_subaction_with_task(self.parent.episode.top_level_action_iri,
                                                                        sub_action_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalAction",
                                                                        task_type="http://www.ease-crc.org/ont/SOMA.owl#PickingUp",
                                                                        start_time=start_time, end_time=end_time)
        return action_iri

    def convert_pregrasp_situation(self, indi) -> str:
        """
        PreGrasp is an ACTION, called "PreGrasp" in the HTML viz, mapped to a PhysicalAction for a task soma:Grasping in SOMA
        """
        start_time = self._extract_timestamp(indi.startTime[0])
        end_time = self._extract_timestamp(indi.endTime[0])
        actor = indi.performedBy[0].iri
        obj = indi.objectActedOn[0].iri
        action_iri = self.parent.neem_interface.add_subaction_with_task(self.parent.episode.top_level_action_iri,
                                                                        sub_action_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalAction",
                                                                        task_type="http://www.ease-crc.org/ont/SOMA.owl#Grasping",
                                                                        start_time=start_time, end_time=end_time)
        self.parent.neem_interface.add_participant_with_role(action_iri, obj, "http://www.ease-crc.org/ont/SOMA.owl#Patient")
        return action_iri

    def convert_put_down_situation(self, indi) -> str:
        # raise NotImplementedError()
        pass

    def convert_reaching_situation(self, indi) -> str:
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
        self.parent.neem_interface.add_participant_with_role(action_iri, obj, "http://www.ease-crc.org/ont/SOMA.owl#GoalRole")
        return action_iri

    def convert_sliding_situation(self, indi) -> str:
        # raise NotImplementedError()
        pass

    def convert_transporting_situation(self, indi) -> str:
        # raise NotImplementedError()
        pass

    def create_anonymous_action(self, start_time: float, end_time: float) -> str:
        action_iri = self.parent.neem_interface.add_subaction_with_task(self.parent.episode.top_level_action_iri,
                                                                        sub_action_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalAction",
                                                                        task_type="http://www.ease-crc.org/ont/SOMA.owl#PhysicalTask",
                                                                        start_time=start_time, end_time=end_time)
        return action_iri

    def _assert_situation_manifesting_at_timestamp(self, timestamp: float, objects: List[str]) -> str:
        situation_iri = self.parent.neem_interface.assert_situation(self.parent.agent, objects,
                                                                    'http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#Situation')
        for state_iri in self.asserted_states:
            res = self.parent.neem_interface.prolog.ensure_once(
                f"kb_call(has_time_interval({atom(state_iri)}, StartTime, EndTime))")
            state_start_time = float(res["StartTime"])
            state_end_time = float(res["EndTime"])
            if state_start_time <= timestamp <= state_end_time:
                self.parent.neem_interface.prolog.ensure_once(
                    f"kb_project(holds({atom(situation_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(state_iri)}))")
        return situation_iri

    def _assert_situation_transition_manifesting_during_interval(self, start_time, end_time) -> str:
        situation_transition_iri = self.parent.neem_interface.assert_situation(self.parent.agent, [],
                                                                               'http://www.ease-crc.org/ont/SOMA.owl#SituationTransition')
        for state_iri in self.asserted_states:
            res = self.parent.neem_interface.prolog.ensure_once(
                f"kb_call(has_time_interval({atom(state_iri)}, StartTime, EndTime))")
            state_start_time = float(res["StartTime"])
            state_end_time = float(res["EndTime"])
            if not (end_time < state_start_time or state_end_time < start_time):
                # There is some overlap with a state
                self.parent.neem_interface.prolog.ensure_once(
                    f"kb_project(holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(state_iri)}))")
        return situation_transition_iri

    def _assert_situation_transition_for_action(self, action_iri: str, initial_situation: str,
                                                terminal_situation: str) -> str:
        res = self.parent.neem_interface.prolog.ensure_once(f"kb_call(has_time_interval({atom(action_iri)}, StartTime, EndTime))")
        start_time = float(res["StartTime"])
        end_time = float(res["EndTime"])
        situation_transition_iri = self._assert_situation_transition_manifesting_during_interval(start_time, end_time)
        self.parent.neem_interface.prolog.ensure_once(f"""
            kb_project([
                holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasInitialSituation', {atom(initial_situation)}),
                holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#hasTerminalSituation', {atom(terminal_situation)}),
                holds({atom(situation_transition_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(action_iri)})
            ])
        """)
        return situation_transition_iri

    def _assert_situation_for_state(self, state_iri: str, objects: List[str]) -> str:
        situation_iri = self.parent.neem_interface.assert_situation(self.parent.agent, objects,
                                                                    'http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#Situation')
        self.parent.neem_interface.prolog.ensure_once(
            f"kb_project(holds({atom(situation_iri)}, 'http://www.ease-crc.org/ont/SOMA.owl#manifestsIn', {atom(state_iri)}))")
        return situation_iri

    def _assert_state(self, participants: List[str], start_time: float, end_time: float,
                      state_type='http://www.ease-crc.org/ont/SOMA.owl#State') -> str:
        if self.parent.agent not in participants:  # Enforce that the agent is always participant of the state
            participants.append(self.parent.agent)
        return self.parent.neem_interface.assert_state(participants, start_time, end_time,
                                                       state_type=state_type)
