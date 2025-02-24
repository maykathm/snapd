#!/usr/bin/env python3

import argparse
import json
import os

def _compose_system(dir, files):
    system = {
        'tests': [],
        'schema-version': '0.0.0',
        'system': 'put system here',
              }
    for file in files:
        with open(os.path.join(dir, file), 'r') as f:
            features = json.loads(f.read())
            test = file.split(':')[2]
            task_variant = "".join(file.split(':')[3:])
            features['suite'] = "/".join(test.split('\\')[:-1])
            features['task-name'] = test.split('\\')[-1]
            features['variant'] = task_variant
            features['scenarios'] = []
            features['env-variables'] = []
            system['tests'].append(features)
    return system


def _get_system_list(dir):
    files = [f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f))]
    systems = [":".join(file.split(':')[:2]) for file in files if file.count(':') == 2]
    return set(systems)

def _get_system_file_list(dir, system):
    return [file for file in os.listdir(dir) if system in file]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dir', type=str, help='Path to the feature-tags folder')
    parser.add_argument('-o', '--output', type=str, help='Output directory')
    parser.add_argument('-s', '--scenarios', type=str, help='Comma-separated list of scenarios')
    parser.add_argument('-e', '--env-variables', type=str, help='Comma-separated list of environment variables as key=value')
    args = parser.parse_args()
    args.dir = '/home/katie/Desktop/tags2/feature-tags'
    args.output = '/home/katie/Desktop/test-output'
    os.makedirs(args.output, exist_ok=True)
    systems = _get_system_list(args.dir)
    for system in systems:
        system_files = _get_system_file_list(args.dir, system)
        composed = _compose_system(args.dir, system_files)
        with open(os.path.join(args.output, system + '.json'), 'w') as f:
            f.write(json.dumps(composed))
        

