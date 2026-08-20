#!/usr/bin/env python3
"""Print a short status summary.

    OMADA_HOST=192.168.0.1 OMADA_USER=admin OMADA_PASSWORD=... python3 example.py
"""
import os
from omada_gateway import OmadaGateway

gw = OmadaGateway(os.environ.get("OMADA_HOST", "192.168.0.1"),
                  os.environ["OMADA_USER"],
                  os.environ["OMADA_PASSWORD"])
gw.login()
try:
    info = gw.get("admin/firmware", "upgrade")["result"]
    print("%s, firmware %s" % (info["hardware_version"], info["firmware_version"]))
    print("CPU %s °C" % gw.get("admin/status", "temperature")["result"]["cpu_temp"])
    print("\n%-6s %-16s %-8s %s" % ("IFACE", "ADDRESS", "PROTO", "LINK"))
    for iface in gw.get("admin/interface", "status2")["result"]["normal"]:
        print("%-6s %-16s %-8s %s" % (iface["t_name"], iface["ipaddr"],
                                      iface["t_proto"], iface["t_isup"]))
finally:
    gw.logout()
