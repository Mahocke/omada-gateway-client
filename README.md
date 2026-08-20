# omada-gateway-client

A small Python client for **TP-Link Omada gateways running standalone** — without
an Omada controller. Pure standard library: no browser, no dependencies. It runs
on a Raspberry Pi as happily as anywhere else.

TP-Link does not offer a REST API for these devices, and the official answer in
their forum is that you should "write your own pseudo-API using the existing web
interface URLs". This is that, with the login already worked out.

## Why the login is the hard part

The web UI encrypts the password with RSA before sending it. Three details make
it awkward to reproduce, and all three cost me an afternoon:

**1. The public key is served without authentication — but not where you'd look.**
Not `form=keys`. It comes from `POST /cgi-bin/luci/;stok=/login?form=login` with
`{"method":"get"}`, which answers `result.password = [modulus, exponent]`.
1024 bit, exponent `0x10001`, and stable across requests.

**2. There is no PKCS#1 padding.** `encrypt.js` calls a function literally named
`nopadding()`: it takes the plaintext bytes, zero-fills them on the *right* up to
the modulus width, and raises that to the public exponent. Textbook RSA. Hand the
same input to a standard RSA library with PKCS#1 padding and the gateway will
reject it.

**3. What gets encrypted is `<password>_<uptime>`, not the password.**
`login.html` configures the password widget with `withTimestamp: true`, and the
widget appends `"_" + $.su.locale.uptime` before encrypting. The uptime comes
from `POST locale?form=lang` with `operation=read`. This is why the ciphertext
looks different on every attempt even though the key is fixed and the algorithm
is deterministic — which is a good way to waste an hour if you assume otherwise.

Get any of the three wrong and the gateway answers `error_code 700`, which means
"wrong credentials" — **and increments a failure counter that eventually locks
the account**. Debug carefully.

After login everything is ordinary JSON:

```
POST /cgi-bin/luci/;stok=<token>/<path>?form=<name>
data={"method":"get"}
```

## Usage

```python
from omada_gateway import OmadaGateway

gw = OmadaGateway("192.168.0.1", "admin", "your-password")
gw.login()
for iface in gw.get("admin/interface", "status2")["result"]["normal"]:
    print(iface["t_name"], iface["ipaddr"], iface["t_isup"])
gw.logout()
```

Or run the example:

```sh
OMADA_HOST=192.168.0.1 OMADA_USER=admin OMADA_PASSWORD=... python3 example.py
```

```
ER707-M2 v1.20, firmware 1.4.5 Build 20260722 Rel.15863
CPU 47 °C

IFACE  ADDRESS          PROTO    LINK
LAN1   192.168.0.1      static   True
WAN1   198.51.100.23    static   True
WAN2   203.0.113.9      dhcp     True
```

### Monitoring

`status_json.py` prints a summary as JSON, which is what you want if a
monitoring system is going to read it:

```sh
python3 status_json.py --env-file /path/to/creds.env --host 192.168.0.1
```

```json
{"ok": true, "model": "ER707-M2", "firmware": "1.4.5 ...", "uptime_s": 1430249,
 "interfaces": [{"name": "WAN1", "address": "198.51.100.23", "up": true}, ...]}
```

On failure it prints `{"ok": false, "error": "..."}` and exits non-zero, so
"gateway unreachable" stays distinguishable from "gateway unhappy". The
`--env-file` option parses `KEY=VALUE` lines itself rather than sourcing them,
so passwords with shell metacharacters cause no trouble.

## Known endpoints

| path | form | returns |
|---|---|---|
| `admin/interface` | `status2` | LAN/WAN with address, protocol, link state |
| `admin/firmware` | `upgrade` | model, hardware and firmware version |
| `admin/status` | `temperature` | CPU temperature |
| `admin/sys_status` | `all_usage` | per-core CPU load |
| `admin/sys_status` | `cpu_num` | number of cores |
| `admin/time` | `settings` | clock, timezone, NTP servers |
| `admin/ipv6` | `wanv6_status_info` | WAN ports with their UI labels |
| `userconfig` | `cfg_save` | HTTPS settings, `controller_mode` |
| `admin/menu` | `advanced_menu` | the full menu tree (**use this to discover more**) |

`admin/menu?form=advanced_menu` returns every page the firmware knows about, which
is the fastest way to find endpoints this table doesn't cover yet.

## Scope

Read-only for now. Write operations use the same transport with `"method": "set"`
or `"add"`, but they are not implemented here — partly because they need
per-endpoint work, partly because getting a WAN operation wrong on a remote
gateway locks you out of the very interface you need to fix it.

## Tested on

**ER707-M2 v1.20, firmware 1.4.5 Build 20260722.** The rest of the family
(ER605, ER706W, ER7206, ER8411) very likely speaks the same protocol, but I have
not tried them. Reports welcome.

## A note on the crypto

Textbook RSA with no padding, using the device's uptime as the only varying
component, is weak: it is deterministic for a given second and malleable. In
practice it matters little, since the whole exchange already runs over HTTPS and
this only obscures the password within that channel. It is worth knowing about
rather than trusting.

This is not a vulnerability report and nothing here bypasses authentication — the
client logs in with valid credentials, and the JavaScript it reproduces is served
to every visitor of the login page.

## Support

There is none. I built this for my own gateways and I am not going to help you
run it. Remarks, bug reports and pull requests are genuinely welcome — especially
test reports from other models — I just make no promise to answer.

## License

MIT. Do whatever you want with it.

TP-Link and Omada are trademarks of TP-Link Systems Inc.; this project is not
affiliated with, endorsed by, or supported by them.

## Writing

Reading was the easy half. Writing has three shapes, and the gateway tells you
almost nothing when you get one wrong — every mistake answers the same
`error_code 15101`, "Incorrect parameters".

**Single records** (`admin/dhcps?form=setting`, and most `?form=…` settings
pages) take the complete record inside `params`. Read-modify-write:

```python
cfg = gw.get("admin/dhcps", "setting")["result"]
cfg.pop("maxleases", None)          # reported, but rejected on the way back
cfg["leasetime"] = "240"
gw.set("admin/dhcps", "setting", cfg)
```

A partial update answers `error_code 15102`. Sending the fields at the top level
instead of inside `params` gets you an HTTP 500 whose body reads
`attempt to index field 'params'` — an unusually honest error message.

**List entries** (address reservations, firewall rules) do *not* follow that
pattern. The fields go into a nested `new` object, and `old` and `id` both carry
the literal string `"add"`:

```python
gw.add("admin/dhcps", "reservation", {
    "mac": "aa-bb-cc-11-22-33", "ip": "192.168.0.32", "note": "desk phone",
    "bind": "1", "ip_bind": "on", "dhcp_option_bind": "off",
    "interface": "LAN1", "enable": "on"})

gw.delete("admin/dhcps", "reservation", key="3", index="1", extra_key="LAN1")
```

I did not derive this. I read it off a request the web UI made, copied out of
Chrome's network panel as cURL. Six attempts at guessing it produced six
identical `15101`s.

## Finding endpoints

`endpoints.txt` lists 524 `path?form=name` pairs. They are not documented
anywhere — they come out of the UI's own bundles, which map every endpoint to a
JSON fixture. Fetch them *with a valid session cookie*; anonymously they come
back empty:

```python
gw.login()
req = urllib.request.Request(gw.base + "/webpages/js/chunk-common.<hash>.js")
req.add_header("Cookie", gw._cookie)
```

The same bundles carry the error-code table in plain text, which is how the
codes below are known.

| Code | Meaning |
|------|---------|
| 700 | wrong credentials — **increments a lockout counter** |
| 1014 | illegal operation (wrong `method` for this endpoint) |
| 15101 | incorrect parameters |
| 15102 | partial update — send the complete record |
| 15104 | invalid MAC or IP |
| 15105 | conflicts with an existing ARP entry |
| 15111 | IP already in the static reservation list |
| 15123 | MAC already bound to another reserved entry |

Verified against an ER707-M2 v1.30, firmware 1.3.2, in standalone mode.
