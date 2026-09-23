#!/usr/bin/env python3
import os
import sys
from gi.repository import GLib
import dbus
import dbus.service

from dbus.mainloop.glib import DBusGMainLoop

DBusGMainLoop(set_as_default=True)


class DBusProvider(dbus.service.Object):
    def __init__(self, bus):
        name = "com.dbustest.HelloWorld"
        instance_key = os.environ.get("SNAP_INSTANCE_KEY")
        if instance_key:
            name += "." + instance_key
        bus_name = dbus.service.BusName(name, bus=bus)
        dbus.service.Object.__init__(self, bus_name, "/com/dbustest/HelloWorld")

    @dbus.service.method(dbus_interface="com.dbustest.HelloWorld", out_signature="s")
    def SayHello(self):
        return "hello world"


if __name__ == "__main__":
    if sys.argv[1] == "system":
        bus = dbus.SystemBus()
    elif sys.argv[1] == "session":
        bus = dbus.SessionBus()
    else:
        print("unknown bus: %s", sys.argv[1:])
        sys.exit(1)
    DBusProvider(bus)
    loop = GLib.MainLoop()
    loop.run()
