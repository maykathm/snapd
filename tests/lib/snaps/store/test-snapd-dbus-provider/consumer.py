#!/usr/bin/env python3
import dbus
import os
import sys


def run(bus):
    name = "com.dbustest.HelloWorld"
    instance_key = os.environ.get("SNAP_INSTANCE_KEY")
    if instance_key:
        name += "." + instance_key
    obj = bus.get_object(name, "/com/dbustest/HelloWorld")
    print(obj.SayHello(dbus_interface="com.dbustest.HelloWorld"))


if __name__ == "__main__":
    if sys.argv[1] == "system":
        bus = dbus.SystemBus()
    else:
        bus = dbus.SessionBus()
    run(bus)
