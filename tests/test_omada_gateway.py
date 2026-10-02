import json
import unittest
from unittest import mock

from omada_gateway import LoginError, OmadaGateway


class Response:
    def __init__(self, body, cookie=None):
        self.body = json.dumps(body).encode()
        self.headers = {"Set-Cookie": cookie} if cookie else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class OmadaGatewayTests(unittest.TestCase):
    def setUp(self):
        self.gw = OmadaGateway("gateway.test", "admin", "secret")

    def test_encrypt_matches_textbook_rsa_and_right_zero_padding(self):
        # Small, artificial modulus: enough to verify the gateway's unusual
        # right-padding convention without depending on a real device.
        modulus = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF61
        exponent = 1
        encrypted = self.gw._encrypt("ab", format(modulus, "x"), format(exponent, "x"))
        self.assertEqual(bytes.fromhex(encrypted), b"ab" + b"\0" * 14)

    def test_encrypt_rejects_plaintext_larger_than_modulus(self):
        with self.assertRaises(ValueError):
            self.gw._encrypt("too long", "ffff", "01")

    @mock.patch("urllib.request.urlopen")
    def test_post_builds_request_and_keeps_session_cookie(self, urlopen):
        urlopen.return_value = Response({"error_code": 0}, "sysauth=abc; Path=/")
        answer = self.gw.get("admin/interface", "status2", {"x": 1})
        self.assertEqual(answer, {"error_code": 0})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/admin/interface?form=status2", request.full_url)
        self.assertEqual(self.gw._cookie, "sysauth=abc")

    def test_write_payload_shapes(self):
        self.gw._post = mock.Mock(return_value={"error_code": 0})
        self.gw.set("admin/dhcps", "setting", {"leasetime": "240"})
        self.gw._post.assert_called_with(
            "admin/dhcps", "setting",
            {"method": "set", "params": {"leasetime": "240"}})

        self.gw.add("admin/dhcps", "reservation", {"ip": "192.0.2.2"}, index=3)
        self.gw._post.assert_called_with(
            "admin/dhcps", "reservation",
            {"method": "add", "params": {
                "index": 3, "old": "add", "id": "add",
                "new": {"ip": "192.0.2.2"}}})

        self.gw.delete("admin/dhcps", "reservation", 7, 2, "LAN1")
        self.gw._post.assert_called_with(
            "admin/dhcps", "reservation",
            {"method": "delete", "params": {
                "key": "7", "index": "2", "extraKey": "LAN1"}})

    def test_login_error_is_explicit(self):
        self.gw.uptime = mock.Mock(return_value=10)
        self.gw.public_key = mock.Mock(return_value=("ff" * 32, "01"))
        self.gw._post = mock.Mock(return_value={"error_code": 700})
        with self.assertRaisesRegex(LoginError, "wrong credentials"):
            self.gw.login()

    def test_successful_login_stores_token(self):
        self.gw.uptime = mock.Mock(return_value=10)
        self.gw.public_key = mock.Mock(return_value=("ff" * 32, "01"))
        self.gw._post = mock.Mock(return_value={
            "error_code": 0, "result": {"stok": "token"}})
        self.assertEqual(self.gw.login(), "token")
        self.assertEqual(self.gw.stok, "token")


if __name__ == "__main__":
    unittest.main()
