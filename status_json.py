#!/usr/bin/env python3
"""Print a machine-readable status summary as JSON. Made for monitoring.

Credentials come from the environment, or from a KEY=VALUE file:

    python3 status_json.py --env-file /path/to/creds.env --host 192.168.0.1

Recognised keys: OMADA_HOST, OMADA_USER, OMADA_PASSWORD.
Exits non-zero and prints {"ok": false, "error": ...} if anything fails, so a
monitoring system can tell "gateway unreachable" from "gateway unhappy".
"""
import argparse
import json
import re
import sys

from omada_gateway import OmadaGateway


def read_env_file(path):
    """Parse KEY=VALUE lines. Quotes optional - no shell involved, so values
    may contain characters that would break `source`."""
    values = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            match = re.match(r"^(\w+)\s*=\s*(.*)$", line)
            if match:
                value = match.group(2).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                values[match.group(1)] = value
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    parser.add_argument("--host")
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args()

    import os
    env = dict(os.environ)
    if args.env_file:
        env.update(read_env_file(args.env_file))

    host = args.host or env.get("OMADA_HOST")
    user = args.user or env.get("OMADA_USER") or env.get("ER707_USER")
    password = args.password or env.get("OMADA_PASSWORD") or env.get("ER707_PASSWORD")
    if not (host and user and password):
        print(json.dumps({"ok": False, "error": "host, user or password missing"}))
        return 2

    gateway = OmadaGateway(host, user, password)
    try:
        gateway.login()
        firmware = gateway.get("admin/firmware", "upgrade")["result"]
        interfaces = gateway.get("admin/interface", "status2")["result"]["normal"]
        result = {
            "ok": True,
            "model": firmware.get("model"),
            "hardware": firmware.get("hardware_version"),
            "firmware": firmware.get("firmware_version"),
            "uptime_s": gateway.uptime(),
            "interfaces": [
                {"name": i.get("t_name"), "label": i.get("t_label"),
                 "address": i.get("ipaddr"), "proto": i.get("t_proto"),
                 "up": bool(i.get("t_isup"))}
                for i in interfaces
            ],
        }
        try:
            result["cpu_temp_c"] = int(
                gateway.get("admin/status", "temperature")["result"]["cpu_temp"])
        except Exception:
            pass
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(error).__name__, error)}))
        return 1
    finally:
        gateway.logout()


if __name__ == "__main__":
    sys.exit(main())
