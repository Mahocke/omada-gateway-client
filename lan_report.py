#!/usr/bin/env python3
"""Liest Pool, Reservierungen und aktuelle Leases eines ER707-M2."""
import sys, urllib.parse, argparse
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from omada_gateway import OmadaGateway


def _cred(creds, *names):
    for n in names:
        if n in creds:
            return creds[n]
    raise SystemExit("Keine Zugangsdaten gefunden, erwartet eines von: " + ", ".join(names))

ap = argparse.ArgumentParser()
ap.add_argument("--host", required=True)
ap.add_argument("--env-file", required=True)
a = ap.parse_args()

creds = {}
for line in open(a.env_file):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        creds[k.strip()] = v.strip().strip("'").strip('"')

gw = OmadaGateway(a.host, _cred(creds, "ER707_USER", "OMADA_USER"), _cred(creds, "ER707_PASSWORD", "OMADA_PASSWORD"))
gw.login()

cfg = gw.get("admin/dhcps", "setting")["result"]
for p in cfg.get("ipRangePool", []):
    print(f"POOL {p['start']} - {p['end']}   Lease {cfg.get('leasetime')} min")

res = gw.get("admin/dhcps", "reservation")["result"] or []
print(f"\n=== {len(res)} RESERVIERUNGEN ===")
for r in sorted(res, key=lambda x: [int(o) for o in x["ip"].split(".")]):
    note = urllib.parse.unquote(r.get("note", ""))
    print(f"  {r['ip']:<15} {r['mac']}  id={r['id']:<3} bind={r['bind']}  {note}")

try:
    cl = gw.get("admin/dhcps", "client")["result"] or []
    print(f"\n=== {len(cl)} AKTUELLE LEASES ===")
    for c in sorted(cl, key=lambda x: [int(o) for o in x.get("ip", "0.0.0.0").split(".")]):
        print(f"  {c.get('ip',''):<15} {c.get('mac','')}  {urllib.parse.unquote(c.get('name',''))}")
except Exception as e:
    print(f"\nLeases nicht lesbar: {e}")

gw.logout()
