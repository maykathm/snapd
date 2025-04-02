#!/usr/bin/env python3

import argparse
from collections import defaultdict
import json
from typing import Any, TextIO

from features import *


def _check_msg(json_entry: dict[str, Any], msg: str) -> bool:
    return 'msg' in json_entry and json_entry['msg'] == msg


def _get_first_task_from_change_containing_task_id(id: str, state_json: dict[str, Any]) -> str:
    for _, data in state_json['changes'].items():
        if id in data['task-ids']:
            return data['task-ids'][0]
    raise RuntimeError("Could not find change for task id {}".format(id))


def _get_snap_type_from_task_id(id: str, state_json: dict[str, Any]) -> str:
    try:
        task_data = state_json['tasks'][id]['data']
    except KeyError as e:
        raise RuntimeError(
            'Cannot find task data in the state.json for task {}'.format(id))
    try:
        if 'snap-type' in task_data:
            return task_data['snap-type']
        elif 'snap-setup' in task_data:
            return task_data['snap-setup']['type']
        elif 'snap-setup-task' in task_data:
            return state_json['tasks'][task_data['snap-setup-task']]['data']['snap-setup']['type']
    except KeyError as e:
        raise RuntimeError(
            'Could not find required keys in task data entry {}'.format(task_data))
    raise RuntimeError(
        'Could not identify snap type of task {} with task data {}'.format(id, task_data))


class CmdFeature:
    name = 'cmd'
    parent = 'cmds'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        if not _check_msg(json_entry, CmdLogLine.msg):
            return
        try:
            feature_dict[CmdFeature.parent].append(
                Cmd(cmd=json_entry[CmdLogLine.cmd]))
        except KeyError as e:
            raise RuntimeError(
                'cmd entry not found in entry {}: {}'.format(json_entry, e))
        

    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        if CmdFeature.parent in feature_dict:
            l = feature_dict[CmdFeature.parent]
            feature_dict[CmdFeature.parent] = [i for n, i in enumerate(l) if i not in l[n + 1:]]


class EndpointFeature:
    name = 'endpoint'
    parent = 'endpoints'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        if not _check_msg(json_entry, EndpointLogLine.msg):
            return
        try:
            if EndpointLogLine.action in json_entry:
                entry = Endpoint(method=json_entry[EndpointLogLine.method],
                                 path=json_entry[EndpointLogLine.path], 
                                 action=json_entry[EndpointLogLine.action])
            else:
                entry = Endpoint(
                    method=json_entry[EndpointLogLine.method], path=json_entry[EndpointLogLine.path])
            feature_dict[EndpointFeature.parent].append(entry)
        except KeyError as e:
            raise RuntimeError(
                'Endpoint entries not found in entry {}: {}'.format(json_entry, e))
        

    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        if EndpointFeature.parent in feature_dict:
            l = feature_dict[EndpointFeature.parent]
            feature_dict[EndpointFeature.parent] = [i for n, i in enumerate(l) if i not in l[n + 1:]]


class InterfaceFeature:
    name = 'interface'
    parent = 'interfaces'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        if not _check_msg(json_entry, InterfaceLogLine.msg):
            return
        try:
            feature_dict[InterfaceFeature.parent].append(Interface(
                name=json_entry[InterfaceLogLine.interface], 
                plug_snap_type=json_entry[InterfaceLogLine.plug], 
                slot_snap_type=json_entry[InterfaceLogLine.slot]))
        except KeyError as e:
            raise RuntimeError(
                'Interface entries not found in entry {}: {}'.format(json_entry, e))
        

    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        if InterfaceFeature.parent in feature_dict:
            l = feature_dict[InterfaceFeature.parent]
            feature_dict[InterfaceFeature.parent] = [i for n, i in enumerate(l) if i not in l[n + 1:]]


class EnsureFeature:
    name = 'ensure'
    parent = 'ensures'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], _):
        if not _check_msg(json_entry, EnsureLogLine.msg):
            return
        try:
            if EnsureLogLine.func in json_entry:
                for ensure_list in reversed(feature_dict[EnsureFeature.parent]):
                    if ensure_list['manager'] == json_entry[EnsureLogLine.manager]:
                        ensure_list['functions'].append(json_entry[EnsureLogLine.func])
                        break
            else:
                feature_dict[EnsureFeature.parent].append(Ensure(manager=json_entry[EnsureLogLine.manager], functions=[]))

        except KeyError as e:
            raise RuntimeError(
                'Interface entries not found in entry {}: {}'.format(json_entry, e))


    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        pass


class ChangeFeature:
    name = 'change'
    parent = 'changes'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], state_json: dict[str, Any]):
        if not _check_msg(json_entry, ChangeLogLine.msg):
            return
        try:
            change = state_json['changes'][json_entry['id']]
            if 'task-ids' not in change:
                # This is a change that operates on all snaps so no need to include it
                return
            if len(change['task-ids']) == 0:
                raise RuntimeError(
                    'Change {} has no task ids. Cannot find snap type'.format(json_entry))
            snap_type = _get_snap_type_from_task_id(
                change['task-ids'][0], state_json)
            feature_dict[ChangeFeature.parent].append(Change(kind=json_entry[ChangeLogLine.kind], snap_type=snap_type))
        except KeyError as e:
            raise RuntimeError(
                'Change entries not found in entry {}: {}'.format(json_entry, e))
        
    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        pass


class TaskFeature:
    name = 'task'
    parent = 'tasks'

    @staticmethod
    def maybe_add_feature(feature_dict: dict[str, list[Any]], json_entry: dict[str, Any], state_json: dict[str, Any]):
        if not _check_msg(json_entry, TaskLogLine.msg):
            return
        for entry in feature_dict[TaskFeature.parent]:
            if json_entry[TaskLogLine.id] == entry["id"]:
                entry['last_status'] = json_entry[TaskLogLine.status]
                return
        try:
            try:
                snap_type = _get_snap_type_from_task_id(
                    json_entry[TaskLogLine.id], state_json)
            except RuntimeError:
                id = _get_first_task_from_change_containing_task_id(
                    json_entry[TaskLogLine.id], state_json)
                snap_type = _get_snap_type_from_task_id(
                    id, state_json)
            feature_dict[TaskFeature.parent].append(
                Task(id=json_entry[TaskLogLine.id], 
                     kind=json_entry[TaskLogLine.task_name], 
                     last_status=json_entry[TaskLogLine.status], 
                     snap_type=snap_type))
        except KeyError as e:
            raise RuntimeError(
                'Task entries not found in entry {}: {}'.format(json_entry, e))
        
    @staticmethod
    def cleanup_dict(feature_dict: dict[str, list[Any]]):
        if TaskFeature.parent in feature_dict:
            for entry in feature_dict[TaskFeature.parent]:
                del entry['id']
            l = feature_dict[TaskFeature.parent]
            feature_dict[TaskFeature.parent] = [i for n, i in enumerate(l) if i not in l[n + 1:]]


FEATURE_LIST = [CmdFeature, EndpointFeature, InterfaceFeature,
                EnsureFeature, ChangeFeature, TaskFeature]


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
                feature_class.maybe_add_feature(
                    feature_dict, line_json, state_json)
        except json.JSONDecodeError:
            raise RuntimeError("Could not parse line as json: {}".format(line))
        
    for feature_class in feature_classes:
        feature_class.cleanup_dict(feature_dict)

    return feature_dict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""Given a set of features with journal entries, each in json format, and a 
        state.json, this script will search the text file and extract the features. Those 
        features will be saved in a dictionary and written to the indicated file in output.""")
    parser.add_argument('-o', '--output', help='Output file', required=True)
    parser.add_argument(
        '-f', '--feature', help='Features to extract from journal {cmd, task, change, ensure, endpoint, interface}; '
        'can be repeated multiple times', nargs='+')
    parser.add_argument(
        '-j', '--journal', help='Text file containing journal entries', required=True, type=argparse.FileType('r'))
    parser.add_argument(
        '-s', '--state', help='state.json', required=True, type=argparse.FileType('r'))
    args = parser.parse_args()

    try:
        state_json = json.load(args.state)
        feature_dictionary = get_feature_dictionary(
            args.journal, args.feature, state_json)
        json.dump(feature_dictionary, open(args.output, "w"))
    except json.JSONDecodeError:
        raise RuntimeError("The state.json is not valid json")
