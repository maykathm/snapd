
from typing import Any

CHANGES = 'changes'
TASKS = 'tasks'
SNAP_TYPE = 'snap-type'
SNAP_SETUP = 'snap-setup'
SNAP_SETUP_TASK = 'snap-setup-task'
HOOK_SETUP = 'hook-setup'
SIDE_INFO = 'side-info'
DATA = 'data'


class State:

    def __init__(self, state_json: dict[str, Any]):
        self.state = state_json

    def get_change(self, id: str) -> dict[str, Any]:
        try:
            return self.state[CHANGES][id]
        except KeyError:
            raise KeyError('change {} not found in state.json'.format(id))
        

    def get_task(self, id: str) -> dict[str, Any]:
        try:
            return self.state[TASKS][id]
        except KeyError:
            raise KeyError('task {} not found in state.json'.format(id))
        

    def is_snap_and_type_present(self, snap_name: str) -> bool:
        snaps = 'snaps'
        return snaps in self.state[DATA] and snap_name in self.state[DATA][snaps] and 'type' in self.state[DATA][snaps][snap_name]
           
        
    def get_snap_type(self, snap_name: str) -> str:
        try:
            if self.is_snap_and_type_present(snap_name):
                return self.state[DATA]['snaps'][snap_name]['type']
            for id, task in self.state[TASKS].items():
                if DATA not in task:
                    continue
                task_data = task[DATA]
                if SNAP_SETUP in task_data and SIDE_INFO in task_data[SNAP_SETUP] and task_data[SNAP_SETUP][SIDE_INFO]['name'] == snap_name:
                    return task_data[SNAP_SETUP]['type']
        except KeyError:
            pass
        
        return "NOT_FOUND: {}".format(snap_name)
        

    def get_snap_types_from_task_id(self, id: str) -> set[str]:
        task = self.get_task(id)
        data = task['data']
        if SNAP_TYPE in data:
            return {data[SNAP_TYPE]}
        elif SNAP_SETUP in data and 'type' in data[SNAP_SETUP]:
            return {data[SNAP_SETUP]['type']}
        elif SNAP_SETUP in data and SIDE_INFO in data[SNAP_SETUP]:
            return {self.get_snap_type(data[SNAP_SETUP][SIDE_INFO]['name'])}
        elif SNAP_SETUP_TASK in data:
            return self.get_snap_types_from_task_id(data[SNAP_SETUP_TASK])
        elif HOOK_SETUP in data and data[HOOK_SETUP]['snap']:
            return {self.get_snap_type(data[HOOK_SETUP]['snap'])}
        elif 'plug' in data and 'slot' in data:
            return {self.get_snap_type(data['plug']['snap']), self.get_snap_type(data['slot']['snap'])}
        

    def get_snap_types_from_change_id(self, id: str) -> set[str]:
        change = self.get_change(id)
        if 'task-ids' not in change:
            return set()
        tasks = change['task-ids']
        snap_types = set()
        for task in tasks:
            snap_types.update(self.get_snap_types_from_task_id(task))
        return snap_types
