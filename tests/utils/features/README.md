# How to Interact with Feature Tagging Data

## Environment setup

(Optional) Create a virtual environment and activate it

```
$ python3 -m venv <virtual-env-name>
$ source <virtual-env-name>/bin/activate
```

In the Python environment of choice, to install dependencies, run

```
$ pip install -r requirements.txt
```

## GUI

In a python environment with requirements installed, run:
```
$ ./dashboard.py
```

In a browser, navigate to http://127.0.0.1:8050


## CLI


```
$ ./query_features.py
```

### Examples

#### Listing data
List all possible timestamps and systems using a mongodb credentials file, `~/features.json`.
```
$ ./query_features.py list -f ~/features.json
```

#### Exporting data
Export data at timestamps `2025-07-21T16:49:21.184000` and `2025-07-08T11:59:16.460000` from mongodb using the credentials at `~/features.json` to the directory `~/Desktop/features`.
```
$ ./query_features.py export -f ~/features.json -o ~/Desktop/features -t "2025-07-21T16:49:21.184000" "2025-07-08T11:59:16.460000"
```

#### Explore features
Find tests that contain the snap command `snap abort` in all systems at timestamp `2025-07-08T11:59:16.460000` using the mongodb credentials file `~/features.json`.
```
$ ./query_features.py feat find -f ~/features.json -t "2025-07-08T11:59:16.460000" --feat '{"cmd":"abort"}'
```
List all possible features at timestamp `2025-07-08` using local data found in the directory `~/Desktop/features`.
```
$ ./query_features.py feat all -d ~/Desktop/features -t "2025-07-08"
```
List features found in system `ubuntu 25.04` at timestamp `2025-07-08` using local data found in the directory `~/Desktop/features`.
```
$ ./query_features.py feat sys -d ~/Desktop/features/ -t "2025-07-08" -s "openstack:ubuntu-25.04-64"
```

#### Calculate difference in features
Using data from mongodb, calculate the difference in features between system `openstack:ubuntu-20.04-64` and system `openstack:ubuntu-22.04-64`, both at timestamp `2025-07-08T11:59:16.460000`.
```
$ ./query_features.py diff systems -f ~/features.json -t1 "2025-07-08T11:59:16.460000" -t2 "2025-07-08T11:59:16.460000" -s1 'openstack:ubuntu-20.04-64' -s2 'openstack:ubuntu-22.04-64'
```

Using local data in folder `~/Desktop/features`, at timestamp `2025-07-08`, calculate the difference between all possible features and the features for system `openstack:ubuntu-22.04-64`.
```
$ ./query_features.py diff all-features -d ~/Desktop/features -t "2025-07-08" -s "openstack:ubuntu-22.04-64"
```

#### Calculate duplicate features

Using local data in folder `~/Desktop/features` at timestamp `2025-07-08`, calculate the tests whose features are copmletely covered by the set of all other tests (excluding variants of the same test) for system `openstack:arch-linux-64`.
```
$ ./query_features.py dup -d ~/Desktop/features -t "2025-07-08" -s 'openstack:arch-linux-64'
```

#### Calculate feature coverage

Using local data in folder `~/Desktop/features` at timestamp `2026-06-06`, calculate complete feature coverage

```
$ ./query_features.py feat cover -d ~/Desktop/features/ -t 2026-06-06
```

Using local data in folder `~/Desktop/features` at timestamp `2026-06-06`, calculate feature coverage with a total runtime for each system at or under 15 minutes, but force include any features with "refresh" or "install" keywords. Also remove features "cmds" and "interfaces" from consideration.
```
$ ./query_features.py feat cover -d ~/Desktop/features/ -t 2026-06-06 --max-minutes 15 --force-match-keywords refresh install --exclude cmds interfaces
```

## Find the tests that use shared test files

`shared_test_users.py` finds the spread tests affected by changes to shared files under `tests/` (helpers in `tests/lib`, test snaps, tools, ...), by searching the checkout for references to them. A reference from a test's folder selects that test, a reference from another shared file is followed to that file's users, and a reference from a suite's section of `spread.yaml` selects the tests of that suite. References from elsewhere in `spread.yaml` or from `tests/lib/prepare.sh`, `prepare-restore.sh` or `reset.sh` mean the file is used by all tests. When other files under `tests/` have the same name, references qualified with the folder of one of them only (e.g. `$TESTSLIB/image.sh` vs `nested/image.sh`) are not counted. Documentation (`README` files, `*.md`) and the own tests, `spread.yaml` and CI of the projects under `tests/lib/external` are not used by any test.

Run it from the checkout of the change being tested. List the users of the shared files changed since `origin/master`:

```
$ ./tests/utils/features/shared_test_users.py --base origin/master
```

Print the changed files with each shared file replaced by the `task.yaml` of every test that uses it, ready to send to the test-selector service (files used by all tests, and files no reference was found for, such as the fakestore sources, are kept as they are so the service runs everything for them; the report marks the latter as `unresolved`):

```
$ ./tests/utils/features/shared_test_users.py --base origin/master --rewrite
```

The changed files can also be given as a json file with `modified`, `added` and `deleted` lists with `--changed-files`.

To mimic CI with the test-selector service, combine it with `.github/scripts/spread_tests_to_run.py`, which prints the spread tests a `spread-tests.yaml` job would run (the "Setup run tests variable" step): expand its output with `spread -list` to get the tests to send to the service, and send the changed files rewritten with `--rewrite`:

```
$ ./.github/scripts/spread_tests_to_run.py --backend openstack --systems ubuntu-24.04-64 --tasks 'tests/...' --rules main --pr --change overlord/snapstate/snapstate.go
openstack:ubuntu-24.04-64:tests/
```
