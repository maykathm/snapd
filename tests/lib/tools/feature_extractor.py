#!/usr/bin/env python3

import argparse
from collections import defaultdict
import json
from typing import Any, TextIO


def _check_msg(json_entry: dict[str, Any], msg: str) -> bool:
    return "msg" in json_entry and json_entry["msg"] == msg


def _get_first_task_from_change(id: str, state_json: dict[str, Any]):
    change = state_json["changes"][id]
    if "task-ids" not in change:
        # This is a change that operates on all snaps so no need to include it
        return
    if len(change["task-ids"]) == 0:
        raise RuntimeError("change {} has no task ids. Cannot find snap type".format(id))
    return change['task-ids'][0]


def _get_snap_type_from_task_id(id: str, state_json: dict[str, Any]) -> str:
    try:
        task = state_json["tasks"][id]
        task_data = task["data"]
    except KeyError as e:
        raise RuntimeError("cannot find task data in the state.json for task {}".format(id))
    try:
        if "snap-type"in task_data:
            return task_data["snap-type"]
        elif "snap-setup" in task_data:
            return task_data["snap-setup"]["type"]
        elif "snap-setup-task" in task_data:
            return state_json["tasks"][task_data["snap-setup-task"]]["data"]["snap-setup"]["type"]
        else:
            first_task = _get_first_task_from_change(task['change'], state_json)
            return _get_snap_type_from_task_id(first_task, state_json)
    except KeyError as e:
        raise RuntimeError("could not find required keys in task data entry {}".format(task_data))


class CmdFeature:
    name = "cmd"
    parent = "cmds"
    msg = "command-execution"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        try:
            feature_dict[CmdFeature.parent].append({CmdFeature.name:json_entry["cmd"]})
        except KeyError as e:
            raise RuntimeError("cmd entry not found in entry {}: {}".format(json_entry, e))
        

class EndpointFeature:
    name = "endpoint"
    parent = "endpoints"
    msg = "endpoint"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        try:
            entry = {"method":json_entry["method"], "path":json_entry["path"]}
            if "action" in json_entry:
                entry.update({"action":json_entry["action"]})
            feature_dict[EndpointFeature.parent].append(entry)
        except KeyError as e:
            raise RuntimeError("endpoint entries not found in entry {}: {}".format(json_entry, e))
        

class InterfaceFeature:
    name = "interface"
    parent = "interfaces"
    msg = "interface-connection"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        try:
            feature_dict[InterfaceFeature.parent].append({"name":json_entry["interface"], "plug-snap-type":json_entry["plug"], "slot-snap-type":json_entry["slot"]})
        except KeyError as e:
            raise RuntimeError("interface entries not found in entry {}: {}".format(json_entry, e))
        

class EnsureFeature:
    name = "ensure"
    parent = "ensures"
    msg = "ensure"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        try:
            if 'func' not in json_entry:
                feature_dict[EnsureFeature.parent].append({"manager":json_entry["manager"], "functions":[]})
            else:
                for ensure_list in reversed(feature_dict[EnsureFeature.parent]):
                    if ensure_list["manager"] == json_entry["manager"]:
                        ensure_list["functions"].append(json_entry["func"])
                        return
        except KeyError as e:
            raise RuntimeError("ensure entries not found in entry {}: {}".format(json_entry, e))


class ChangeFeature:
    name = "change"
    parent = "changes"
    msg = "new-change"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], state_json: dict[str, Any]):
        try:
            change = state_json["changes"][json_entry["id"]]
            if "task-ids" not in change:
                # This is a change that operates on all snaps so no need to include it
                return
            if len(change["task-ids"]) == 0:
                raise RuntimeError("change {} has no task ids. Cannot find snap type".format(json_entry))
            snap_type = _get_snap_type_from_task_id(change["task-ids"][0], state_json)
            feature_dict[ChangeFeature.parent].append({"kind":json_entry["kind"], "snap-type":snap_type})
        except KeyError as e:
            raise RuntimeError("change entries not found in entry {}: {}".format(json_entry, e))
        

class TaskFeature:
    name = "task"
    parent = "tasks"
    msg = "task-status-change"

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], state_json: dict[str, Any]):
        for entry in feature_dict[TaskFeature.parent]:
            if json_entry["id"] == entry["id"]:
                entry["last-status"] = json_entry["status"]
                return
        try:
            snap_type = _get_snap_type_from_task_id(json_entry["id"], state_json)
            feature_dict[TaskFeature.parent].append({"id": json_entry["id"], "kind":json_entry["task-name"],"last-status":json_entry["status"], "snap-type":snap_type})
        except KeyError as e:
            raise RuntimeError("Task entries not found in entry {}: {}".format(json_entry, e))


FEATURE_LIST = [CmdFeature, EndpointFeature, InterfaceFeature, EnsureFeature, ChangeFeature, TaskFeature]


def get_feature_dictionary(log_file: TextIO, feature_list: list[str], state_json: dict[str, Any]):
    '''
    Extracts features from the journal entries and places them in a dictionary.

    :param log_file: iterator of journal entries
    :param feature_list: list of feature names to extract
    :param state_json: dictionary of a state.json
    :return: dictionary of features
    :raises: ValueError if an invalid feature name is provided
    :raises: RuntimeError if a line could not be parsed as json
    '''
    
    feature_dict = defaultdict(list)
    feature_classes = [cls for cls in FEATURE_LIST
                       if cls.name in feature_list]
    if len(feature_classes) != len(feature_list):
        raise ValueError(
            "Error: Invalid feature name in feature list {}".format(feature_list))

    for line in log_file:
        try:
            line_json = json.loads(line)
            for feature_class in feature_classes:
                if not _check_msg(line_json, feature_class.msg):
                    continue
                feature_class.maybe_add_feature(feature_dict, line_json, state_json)
        except json.JSONDecodeError:
            raise RuntimeError("Could not parse line as json: {}".format(line))
    return feature_dict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""Given a set of features with journal entries, each in json format, and a 
        state.json, this script will search the text file and extract the features. Those 
        features will be saved in a dictionary and written to the indicated file in output.""")
    parser.add_argument('-o', '--output', help='Output file', required=True)
    parser.add_argument(
        '-f', '--feature', help='Features to extract from journal {all}; can be repeated multiple times', nargs='+')
    parser.add_argument(
        '-j', '--journal', help='Text file containing journal entries', required=True, type=argparse.FileType('r'))
    parser.add_argument(
        '-s', '--state', help='state.json', required=True, type=argparse.FileType('r'))
    args = parser.parse_args()

    try:
        state_json = json.load(args.state)
        feature_dictionary = get_feature_dictionary(args.journal, args.feature, state_json)
        json.dump(feature_dictionary, open(args.output, "w"))
    except json.JSONDecodeError:
        raise RuntimeError("The state.json is not valid json")
