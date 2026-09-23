#!/usr/bin/env python3
import dbus
import os
import subprocess
import sys
from pathlib import Path


def run(bus):
    if len(sys.argv) > 2:
        name = sys.argv[2]
    else:
        filename = "dbus-system-test-name" if sys.argv[1] == "system" else "dbus-test-name"
        name_file = Path(os.environ["SNAP_DATA"]) / filename
        if name_file.exists():
            name = name_file.read_text().strip()
        else:
            slot = ":dbus-system-test" if sys.argv[1] == "system" else ":dbus-test"
            name = subprocess.check_output(
                ["snapctl", "get", "--slot", slot, "name"], text=True
            ).strip()
    obj = bus.get_object(name, "/com/dbustest/HelloWorld")
    print(obj.SayHello(dbus_interface="com.dbustest.HelloWorld"))


if __name__ == "__main__":
    if sys.argv[1] == "system":
        bus = dbus.SystemBus()
    else:
        bus = dbus.SessionBus()
    run(bus)
