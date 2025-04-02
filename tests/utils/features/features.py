
'''
Dictionaries to specify structure of feature logs
'''

from enum import Enum
from typing import TypedDict


class Cmd(TypedDict):
    cmd: str


class Endpoint(TypedDict):
    method: str
    path: str
    action: str


class Interface(TypedDict):
    name: str
    plug_snap_type: str
    slot_snap_type: str


class Status(str, Enum):
    done = "Done"
    undone = "Undone"
    error = "Error"

class Task(TypedDict):
    id: str
    kind: str
    snap_type: str
    last_status: str


class Change(TypedDict):
    kind: str
    snap_type: str


class Ensure(TypedDict):
    manager: str
    functions: list[str]


class EnvVariables(TypedDict):
    name: str
    value: str

class TaskFeatures(TypedDict):
    suite: str
    task_name: str
    variant: str
    success: bool
    cmds: list[Cmd]
    endpoints: list[Endpoint]
    interfaces: list[Interface]
    tasks: list[Task]
    changes: list[Change]
    ensures: list[Ensure]


class SystemFeatures(TypedDict):
    schema_version: str
    system: str
    scenarios: list[str]
    env_variables: list[EnvVariables]
    tests: list[TaskFeatures]


class CmdLogLine:
    msg = 'executing-command'
    cmd = 'cmd'


class EndpointLogLine:
    msg = 'endpoint'
    method = 'method'
    path = 'path'
    action = 'action'


class InterfaceLogLine:
    msg = 'interface-connection'
    interface = 'interface'
    slot = 'slot'
    plug = 'plug'


class EnsureLogLine:
    msg = 'ensure'
    manager = 'manager'
    func = 'func'


class TaskLogLine:
    msg = 'task-status-change'
    task_name = 'task-name'
    id = 'id'
    status = 'status'


class ChangeLogLine:
    msg = 'new-change'
    kind = 'kind'
    id = 'id'
