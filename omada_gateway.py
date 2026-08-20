#!/usr/bin/env python3
"""Client for TP-Link Omada gateways running in standalone mode (no controller).

TP-Link offers no REST API for these devices. This talks to the same endpoints
the web UI uses. Pure standard library - no browser, no dependencies - so it
runs on a Raspberry Pi just as well as anywhere else.

See README.md for how the login was worked out.
"""
import json
import ssl
import urllib.parse
import urllib.request

__all__ = ["OmadaGateway", "LoginError"]
__version__ = "0.1.0"


class LoginError(RuntimeError):
    """Raised when the gateway rejects the login."""


class OmadaGateway:
    """Minimal client for the standalone web interface.

    >>> gw = OmadaGateway("192.168.0.1", "admin", "secret")
    >>> gw.login()
    >>> gw.get("admin/interface", "status2")["result"]["normal"]
    >>> gw.logout()
    """

    def __init__(self, host, username, password, verify_tls=False, timeout=15):
        self.base = "https://%s" % host
        self.username = username
        self.password = password
        self.timeout = timeout
        self.stok = None
        self._cookie = None
        self._ssl = None if verify_tls else ssl._create_unverified_context()

    # -- plumbing ---------------------------------------------------------

    def _post(self, path, form, payload=None, raw=None):
        url = "%s/cgi-bin/luci/;stok=%s/%s?form=%s" % (
            self.base, self.stok or "", path, form)
        body = raw if raw is not None else urllib.parse.urlencode(
            {"data": json.dumps(payload)})
        request = urllib.request.Request(url, data=body.encode(), method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        request.add_header("Referer", self.base + "/webpages/login.html")
        if self._cookie:
            request.add_header("Cookie", self._cookie)
        with urllib.request.urlopen(request, context=self._ssl,
                                    timeout=self.timeout) as response:
            set_cookie = response.headers.get("Set-Cookie")
            if set_cookie:
                self._cookie = set_cookie.split(";")[0]
            return json.loads(response.read().decode())

    @staticmethod
    def _encrypt(text, modulus_hex, exponent_hex):
        """Reproduce the gateway's encrypt.js.

        It uses `nopadding()`: the plaintext bytes are zero-filled on the RIGHT
        up to the modulus width, then raised to the public exponent. That is
        textbook RSA - no PKCS#1, no random padding. Using a standard RSA
        library with PKCS#1 padding here will always fail.
        """
        modulus, exponent = int(modulus_hex, 16), int(exponent_hex, 16)
        width = (modulus.bit_length() + 7) // 8
        message = text.encode()
        if len(message) > width:
            raise ValueError("plaintext longer than the modulus")
        block = message + b"\x00" * (width - len(message))
        cipher = format(pow(int.from_bytes(block, "big"), exponent, modulus), "x")
        return cipher if len(cipher) % 2 == 0 else "0" + cipher

    # -- public API -------------------------------------------------------

    def uptime(self):
        """Seconds since boot. Part of the login secret - see login()."""
        return self._post("locale", "lang", raw="operation=read")["result"]["uptime"]

    def public_key(self):
        """(modulus, exponent) as hex strings. Served without authentication."""
        return self._post("login", "login", {"method": "get"})["result"]["password"]

    def login(self):
        """Authenticate and remember the session token.

        The gateway does not encrypt the password alone: login.html configures
        the password widget with `withTimestamp: true`, so what actually gets
        encrypted is `<password>_<uptime>`. Without the uptime the gateway
        answers error_code 700 - and counts it as a failed attempt.
        """
        secret = "%s_%s" % (self.password, self.uptime())
        modulus, exponent = self.public_key()
        answer = self._post("login", "login", {
            "method": "login",
            "params": {"username": self.username,
                       "password": self._encrypt(secret, modulus, exponent)},
        })
        code = answer.get("error_code")
        if str(code) != "0":
            raise LoginError(
                "login refused, error_code %s%s" % (
                    code, " (700 = wrong credentials)" if str(code) == "700" else ""))
        self.stok = answer["result"]["stok"]
        return self.stok

    def get(self, path, form, params=None):
        """Read an endpoint, e.g. get("admin/interface", "status2")."""
        payload = {"method": "get"}
        if params is not None:
            payload["params"] = params
        return self._post(path, form, payload)

    def logout(self):
        try:
            self._post("login", "logout", {"method": "logout"})
        except Exception:
            pass
        self.stok = None
