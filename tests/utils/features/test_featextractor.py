
import argparse
import os
import sys
# To ensure the unit test can be run from any point in the filesystem,
# add parent folder to path to permit relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
from io import StringIO
from typing import Any
import unittest
from unittest.mock import Mock, patch
from tempfile import TemporaryFile

import featextractor
from featextractor import CmdFeature, EndpointFeature, InterfaceFeature, TaskFeature, ChangeFeature, EnsureFeature 
from features import *
from state import State

def _get_stringio_from_loglines(loglines: list[dict]):
    lines=""
    for line in loglines:
        lines+=json.dumps(line) + "\n"
    return StringIO(lines)


class TestExtract(unittest.TestCase):
    

    def test_extract_cmd(self):
        cmd = "info snap"
        loglines = [{"msg":CmdFeature.msg, CmdLogLine.cmd:cmd}]
        logs = _get_stringio_from_loglines(loglines)
        d = featextractor.get_feature_dictionary(logs, ['cmd'], State({}))
        self.assertDictEqual({"cmds":[Cmd(cmd=cmd)]}, d)

    def test_extract_endpoint(self):
        method = "GET"
        path = "/v2/snap/{info}"
        loglines = [{"msg":EndpointFeature.msg, EndpointLogLine.method:method, EndpointLogLine.path:path}]
        logs = _get_stringio_from_loglines(loglines)
        d = featextractor.get_feature_dictionary(logs, ['endpoint'], State({}))
        self.assertDictEqual({"endpoints":[Endpoint(method=method, path=path)]}, d)

    def test_extract_endpoint_with_action(self):
        method = "POST"
        path = "/v2/snap/{id}"
        action = "update"
        loglines = [{"msg":EndpointFeature.msg, EndpointLogLine.method:method, EndpointLogLine.path:path, EndpointLogLine.action:action}]
        logs = _get_stringio_from_loglines(loglines)
        d = featextractor.get_feature_dictionary(logs, ['endpoint'], State({}))
        self.assertDictEqual({"endpoints":[Endpoint(method=method, path=path, action=action)]}, d)

    def test_extract_interface(self):
        name = 'my-interface'
        plug = 'app'
        slot = 'snapd'
        loglines = [{"msg":InterfaceFeature.msg, InterfaceLogLine.interface:name, InterfaceLogLine.plug:plug, InterfaceLogLine.slot:slot}]
        logs = _get_stringio_from_loglines(loglines)
        d = featextractor.get_feature_dictionary(logs, ['interface'], State({}))
        self.assertDictEqual({"interfaces":[Interface(name=name, plug_snap_type=plug, slot_snap_type=slot)]}, d)

    def test_extract_ensure(self):
        mgr = 'my-manager'
        loglines = [
            {"msg":EnsureFeature.msg, EnsureLogLine.manager:mgr},
            {"msg":EnsureFeature.msg, EnsureLogLine.manager:mgr, EnsureLogLine.func:'1'},
            {"msg":EnsureFeature.msg, EnsureLogLine.manager:mgr, EnsureLogLine.func:'2'},
            {"msg":EnsureFeature.msg, EnsureLogLine.manager:mgr},
            {"msg":EnsureFeature.msg, EnsureLogLine.manager:mgr, EnsureLogLine.func:'3'},
                    ]
        logs = _get_stringio_from_loglines(loglines)
        d = featextractor.get_feature_dictionary(logs, ['ensure'], State({}))
        self.assertDictEqual({"ensures":[
            Ensure(manager=mgr, functions=['1','2']),
            Ensure(manager=mgr, functions=['3'])]}
                             , d)
        
    def test_extract_task(self):
        loglines = [
            {"msg":TaskFeature.msg, TaskLogLine.id:"1", TaskLogLine.task_name:"kind1", TaskLogLine.status:"Doing"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"2", TaskLogLine.task_name:"kind2", TaskLogLine.status:"Doing"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"1", TaskLogLine.task_name:"kind1", TaskLogLine.status:"Done"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"3", TaskLogLine.task_name:"kind3", TaskLogLine.status:"Doing"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"3", TaskLogLine.task_name:"kind3", TaskLogLine.status:"Undoing"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"3", TaskLogLine.task_name:"kind3", TaskLogLine.status:"Undone"},
            {"msg":TaskFeature.msg, TaskLogLine.id:"2", TaskLogLine.task_name:"kind2", TaskLogLine.status:"Error"},
        ]
        logs = _get_stringio_from_loglines(loglines)
        state = {
            "tasks":{
                "1":{"data":{"snap-setup":{"type":"snapd"}}},
                "2":{"data":{"snap-type":"app"}},
                "3":{"data":{"snap-setup-task":"1"}}},
            }
        d = featextractor.get_feature_dictionary(logs, ['task'], State(state))
        self.assertDictEqual({"tasks":[
            Task(kind="kind1", snap_types=["snapd"], last_status=Status.done.value),
            Task(kind="kind2", snap_types=["app"], last_status=Status.error.value),
            Task(kind="kind3", snap_types=["snapd"], last_status=Status.undone.value),
        ]}, d)
        
    def test_extract_change(self):
        loglines = [
            {"msg":ChangeFeature.msg, ChangeLogLine.id:"1", ChangeLogLine.kind:"kind1"},
            {"msg":ChangeFeature.msg, ChangeLogLine.id:"2", ChangeLogLine.kind:"kind2"},
            {"msg":ChangeFeature.msg, ChangeLogLine.id:"3", ChangeLogLine.kind:"kind3"},
        ]
        logs = _get_stringio_from_loglines(loglines)
        state = {
            "changes":{
                "1":{"task-ids":["11"]},
                "2":{"task-ids":["12"]},
                "3":{},
            },
            "tasks":{
                "11":{"data":{"snap-setup":{"type":"snapd"}}},
                "12":{"data":{"snap-type":"app"}}
            }}
        d = featextractor.get_feature_dictionary(logs, ['change'], State(state))
        self.assertDictEqual({"changes":[
            Change(kind="kind1", snap_types=["snapd"]),
            Change(kind="kind2", snap_types=["app"]),
            Change(kind="kind3", snap_types=[])
        ]}, d)
        
    @patch('argparse.ArgumentParser.parse_args')
    def test_interfaces_avahi_observe(self, parse_args_mock: Mock):
        output_file = '/tmp/outthings.json'
        with open(os.path.join('interfaces-avahi-observe', 'state.json'), 'r', encoding='utf-8') as fpstate:
            with open(os.path.join('interfaces-avahi-observe', 'journal.txt'), 'r', encoding='utf-8') as fpjournal:
                parse_args_mock.return_value = argparse.Namespace(
                    feature=['cmd','ensure','interface','task','change','endpoint'],
                    journal=fpjournal,
                    state = fpstate,
                    output=output_file
                )
                featextractor.main()
        with open(output_file, 'r') as f:
            result = json.load(f)
            i = 0


if __name__ == '__main__':
    unittest.main()
