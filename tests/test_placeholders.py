""".env.example ships <API_KEY> and <BEARER_TOKEN>. A user who copies it to .env
and forgets one must get a refusal naming the variable -- never a deployment
where the literal placeholder text works as a password."""
from __future__ import annotations

import re
import sys
import unittest
from unittest import mock

from _env import ROOT  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maxey0_ss.adapters.a2a import a2a_credential_valid  # noqa: E402
from maxey0_ss.auth.policy import AuthError, Authorizer, is_placeholder_secret  # noqa: E402
from maxey0_ss.providers.base import is_placeholder  # noqa: E402


def _example_values() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2).strip()
    return values


class ShippedPlaceholders(unittest.TestCase):
    def test_every_credential_line_ships_a_recognized_placeholder(self):
        values = _example_values()
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"):
            with self.subTest(name=name):
                self.assertEqual(values[name], "<API_KEY>")
                self.assertTrue(is_placeholder(values[name]))
        for name in ("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", "MAXEY0_A2A_SHARED_SECRET"):
            with self.subTest(name=name):
                self.assertEqual(values[name], "<BEARER_TOKEN>")
                self.assertTrue(is_placeholder_secret(values[name]))


class APlaceholderIsNeverAPassword(unittest.TestCase):
    def _authorizer(self, **env):
        base = {"MAXEY0_AUTH_MODE": "bearer", "MAXEY0_PUBLIC": "1",
                "MAXEY0_MCP_TOKENS": "", "MAXEY0_MCP_TOKEN_HASHES": "",
                "MAXEY0_MCP_DEFAULT_BEARER_TOKEN": ""}
        base.update(env)
        with mock.patch.dict("os.environ", base):
            from maxey0_ss.auth.config import AuthConfig
            return Authorizer(AuthConfig.load(credentials={}))

    def test_the_default_bearer_placeholder_refuses_every_request(self):
        auth = self._authorizer(MAXEY0_MCP_DEFAULT_BEARER_TOKEN="<BEARER_TOKEN>")
        for header in ("Bearer <BEARER_TOKEN>", "Bearer anything", None):
            with self.subTest(header=header):
                with self.assertRaises(AuthError) as caught:
                    auth.principal(header)
                self.assertEqual(caught.exception.status, 501)
                self.assertIn("MAXEY0_MCP_DEFAULT_BEARER_TOKEN", str(caught.exception))

    def test_a_placeholder_in_the_plaintext_list_refuses(self):
        # Tokens are parsed on first use, so the request must run while the
        # variable is still set.
        with mock.patch.dict("os.environ", {"MAXEY0_MCP_TOKENS": "<BEARER_TOKEN>:admin"}):
            auth = self._authorizer(MAXEY0_MCP_TOKENS="<BEARER_TOKEN>:admin")
            with self.assertRaises(AuthError) as caught:
                auth.principal("Bearer <BEARER_TOKEN>")
        self.assertEqual(caught.exception.status, 501)
        self.assertIn("placeholder", str(caught.exception))

    def test_the_a2a_placeholder_is_never_a_valid_secret(self):
        for presented in ("Bearer <BEARER_TOKEN>", "<BEARER_TOKEN>", "Bearer x", None):
            with self.subTest(presented=presented):
                self.assertFalse(a2a_credential_valid(presented, "<BEARER_TOKEN>"))

    def test_a_real_token_is_not_mistaken_for_a_placeholder(self):
        real = "m0ss_" + "Axxxx" + "Q" * 38   # contains 'xxxx', as random tokens can
        self.assertFalse(is_placeholder_secret(real))
        auth = self._authorizer(MAXEY0_MCP_DEFAULT_BEARER_TOKEN=real)
        self.assertEqual(auth.principal("Bearer " + real).role, "operator")
        self.assertTrue(a2a_credential_valid("Bearer " + real, real))


if __name__ == "__main__":
    unittest.main()
