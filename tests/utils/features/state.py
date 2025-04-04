
from typing import Any


class State:

    def __init__(self, state_json: dict[str, Any]):
        self.state = state_json

    def get_change(self, id: str) -> dict[str, Any]:
        try:
            return self.state['changes'][id]
        except KeyError:
            raise KeyError('change {} not found in state.json'.format(id))
        

    def get_task(self, id: str) -> dict[str, Any]:
        try:
            return self.state['tasks'][id]
        except KeyError:
            raise KeyError('task {} not found in state.json'.format(id))
        
    def get_snap_type(self, snap_name: str) -> dict[str, Any]:
        try:
            return self.state['data']['snaps'][snap_name]['type']
        except KeyError:
            raise KeyError('snap type for {} not found'.format(snap_name))
        

    def get_snap_types_from_task_id(self, id: str) -> set[str]:
        task = self.get_task(id)
        data = task['data']
        if 'snap-type' in data:
            return {data['snap-type']}
        elif 'snap-setup' in data:
            return {data['snap-setup']['type']}
        elif 'snap-setup-task' in data:
            return self.get_snap_types_from_task_id(data['snap-setup-task'])
        elif 'hook-setup' in data:
            return {self.get_snap_type(data['hook-setup']['snap'])}
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
        

    # def _get_first_task_from_change_containing_task_id(id: str, state_json: dict[str, Any]) -> str:
    #     for _, data in state_json['changes'].items():
    #         if id in data['task-ids']:
    #             return data['task-ids'][0]
    #     raise RuntimeError("Could not find change for task id {}".format(id))


    # def _get_snap_type_from_task_id(id: str, state_json: dict[str, Any]) -> str:
    #     try:
    #         task_data = state_json['tasks'][id]['data']
    #     except KeyError as e:
    #         raise RuntimeError(
    #             'Cannot find task data in the state.json for task {}'.format(id))
    #     try:
    #         if 'snap-type' in task_data:
    #             return task_data['snap-type']
    #         elif 'snap-setup' in task_data:
    #             return task_data['snap-setup']['type']
    #         elif 'snap-setup-task' in task_data:
    #             return state_json['tasks'][task_data['snap-setup-task']]['data']['snap-setup']['type']
    #     except KeyError as e:
    #         raise RuntimeError(
    #             'Could not find required keys in task data entry {}'.format(task_data))
    #     raise RuntimeError(
    #         'Could not identify snap type of task {} with task data {}'.format(id, task_data))