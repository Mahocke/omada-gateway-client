#!/usr/bin/env python3
"""Legt EINE Adressreservierung auf einem ER707-M2 an. Idempotent: vorhandene
MAC oder IP wird uebersprungen, nichts wird geloescht. Ohne --apply nur Trockenlauf."""
import sys, urllib.parse, argparse
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from omada_gateway import OmadaGateway

def _cred(creds, *names):
    for n in names:
        if n in creds:
            return creds[n]
    raise SystemExit("Keine Zugangsdaten gefunden, erwartet: " + ", ".join(names))

ap = argparse.ArgumentParser()
ap.add_argument("--host", required=True)
ap.add_argument("--env-file", required=True)
ap.add_argument("--mac", required=True)
ap.add_argument("--ip", required=True)
ap.add_argument("--note", default="")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

creds = {}
for line in open(a.env_file):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        creds[k.strip()] = v.strip().strip("'").strip('"')

gw = OmadaGateway(a.host, _cred(creds, "ER707_USER", "OMADA_USER"),
                          _cred(creds, "ER707_PASSWORD", "OMADA_PASSWORD"))
gw.login()
try:
    vorher = gw.get("admin/dhcps", "reservation")["result"] or []
    mac = a.mac.upper().replace(":", "-")

    if mac in {r["mac"].upper() for r in vorher}:
        print(f"  uebersprungen — MAC {mac} ist bereits reserviert")
    elif a.ip in {r["ip"] for r in vorher}:
        print(f"  uebersprungen — Adresse {a.ip} ist bereits vergeben")
    elif not a.apply:
        print(f"  [trocken] wuerde anlegen: {a.ip}  {mac}  {a.note}")
    else:
        gw.add("admin/dhcps", "reservation", {
            "mac": mac, "ip": a.ip, "note": urllib.parse.quote(a.note),
            "bind": "0", "ip_bind": "on", "dhcp_option_bind": "off",
            "interface": "LAN1", "enable": "on",
        })
        print(f"  angelegt: {a.ip}  {mac}  {a.note}")

    nachher = gw.get("admin/dhcps", "reservation")["result"] or []
    print(f"\n{len(nachher)} Reservierungen:")
    for r in sorted(nachher, key=lambda x: [int(o) for o in x["ip"].split(".")]):
        print(f"  {r['ip']:<15} {r['mac']}  {urllib.parse.unquote(r.get('note',''))}")
    gw.logout()
finally:
    try:
        gw.logout()
    except Exception:
        pass
