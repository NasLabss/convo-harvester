# -*- coding: utf-8 -*-
"""Unit tests for sanitization (convo_harvester.sanitize).

No external dependencies: unittest only (standard library).
The expected behavior is locked to the reference module of
memory-harvester (audited 18/18): redact_text is applied by render_md
before any write to disk.

Run with:
    python3 -m unittest tests.test_sanitize -v
or  python3 tests/test_sanitize.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convo_harvester.sanitize import (  # noqa: E402
    REDACTED,
    SANITIZE_EXTENSIONS,
    _is_sensitive_key,
    _sanitizable_extension,
    redact_text,
    redact_value,
)
from convo_harvester.render import render_md  # noqa: E402


class TestKnownTokens(unittest.TestCase):
    """Known token formats (Anthropic, OpenAI, Stripe, HuggingFace,
    npm, GitHub, GitLab, Slack, Google, AWS...)."""

    def test_openai_sk_long_dash(self):
        out = redact_text("email jean@exemple.com et "
                          "sk-" "abcdefghijklmnopqrstuvwxyz12345")
        self.assertEqual(out, "email " + REDACTED + " et " + REDACTED)

    def test_openai_sk_generic_20plus(self):
        """Generic sk- token: redacted from 20 characters onward."""
        out = redact_text("cle " "sk-" "abc123def456789ghijkl")
        self.assertEqual(out, "cle " + REDACTED)

    def test_openai_sk_short_no_prefix_kept(self):
        """Behavior locked to the reference module:
        a 12-character 'sk-' WITHOUT a live/test/ant/proj prefix is not
        detected (the pattern requires either the prefix or >= 20 characters)."""
        self.assertEqual(redact_text("cle sk-abc123def456"), "cle sk-abc123def456")

    def test_openai_sk_underscore_live(self):
        self.assertEqual(redact_text("sk_live_" "abcdefghijklmnopqrstuvwxyz"),
                         REDACTED)

    def test_anthropic_sk_ant(self):
        self.assertEqual(redact_text("sk-ant-" "api03-abcdefghijklmnopqrstuvwxyz1234567890"),
                         REDACTED)

    def test_anthropic_sk_proj(self):
        self.assertEqual(redact_text("sk-proj-" "abcdefghijklmnopqrstuvwxyz1234567890"),
                         REDACTED)

    def test_huggingface(self):
        self.assertEqual(redact_text("hf_" "abcdefghijklmnopqrstuvwxyz"), REDACTED)

    def test_npm(self):
        self.assertEqual(redact_text("npm_" "abcdefghijklmnopqrstuvwxyz"), REDACTED)

    def test_stripe_rk(self):
        self.assertEqual(redact_text("rk_live_" "abcdefghijklmnopqrstuvwxyz"),
                         REDACTED)

    def test_stripe_whsec(self):
        self.assertEqual(redact_text("whsec_" "abcdefghijklmnopqrstuvwxyz"),
                         REDACTED)

    def test_github_pat(self):
        self.assertEqual(redact_text("github_pat_" "abcdefghijklmnopqrstuvwxyz"),
                         REDACTED)

    def test_github_oauth(self):
        self.assertEqual(redact_text("gho_" "abcdefghijklmnopqrstuvwxyz"), REDACTED)

    def test_gitlab_pat(self):
        self.assertEqual(redact_text("glpat-" "abcdefghijklmnopqrstuv"), REDACTED)

    def test_slack_token(self):
        self.assertEqual(redact_text("xoxb-" "abcdefghijklmnopqrstuvwxyz"),
                         REDACTED)

    def test_google_aiza(self):
        self.assertEqual(redact_text("AIza" "SyABCDEFGHIJKLMNOPQRSTUVWXYZ012345"),
                         REDACTED)

    def test_aws_akia(self):
        self.assertEqual(redact_text("AKIA" "IOSFODNN7EXAMPLE"), REDACTED)

    def test_no_residue(self):
        """The secret value must NEVER appear in the output."""
        secret = "sk-" "abcdefghijklmnopqrstuvwxyz12345"
        self.assertNotIn(secret, redact_text(f"token {secret} dans du texte"))


class TestStructuredSecrets(unittest.TestCase):
    def test_private_key_pem(self):
        pem = ("-----BEGIN " "PRIVATE KEY-----\n"
               "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
               "-----END " "PRIVATE KEY-----" "\n")
        # The trailing \n is not covered by the DOTALL pattern: behavior
        # locked to the reference module.
        self.assertEqual(redact_text(pem), REDACTED + "\n")

    def test_authorization_header(self):
        out = redact_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456")
        # _SENSITIVE_HEADER_RE consumes the whole line (Bearer + token included).
        self.assertEqual(out, "Authorization: " + REDACTED)

    def test_cookie_header(self):
        self.assertEqual(redact_text("cookie: session=abc123def456"),
                         "cookie: " + REDACTED)

    def test_env_secret(self):
        self.assertEqual(redact_text("OPENAI_API_KEY=" "sk-" "abcdefghijklmnopqrstuvwxyz12345"),
                         "OPENAI_API_KEY=" + REDACTED)

    def test_env_export_secret(self):
        self.assertEqual(redact_text("export DATABASE_URL=postgres://user:pass@host/db"),
                         "export DATABASE_URL=" + REDACTED)

    def test_npmrc_auth_token(self):
        self.assertEqual(redact_text("//registry.npmjs.org/:_authToken=" "npm_" "abcdefghijklmnopqrstuvwxyz"),
                         "//registry.npmjs.org/:_authToken=" + REDACTED)

    def test_json_quoted_label(self):
        self.assertEqual(redact_text('{"apiKey": "' "sk-" "abcdefghijklmnopqrstuvwxyz12345" '"}'),
                         '{"apiKey": ' + REDACTED + "}")

    def test_json_bare_label(self):
        self.assertEqual(redact_text('{"client_secret": abcdefghijklmnopqrstuvwxyz123456}'),
                         '{"client_secret": ' + REDACTED + "}")

    def test_query_string(self):
        self.assertEqual(redact_text("https://example.com/?api_key=" "sk-" "abcdefghijklmnopqrstuvwxyz12345" "&x=1"),
                         "https://example.com/?api_key=" + REDACTED)

    def test_url_userinfo(self):
        self.assertEqual(redact_text("postgres://user:mypassword@localhost:5432/db"),
                         "postgres://" + REDACTED + "@localhost:5432/db")

    def test_discord_webhook(self):
        self.assertEqual(
            redact_text("https://discord.com/api/webhooks/123456789012345678/"
                        "abcDEFghIJK_lmnOPQRStuVWXyz0123456789-AB"),
            REDACTED)

    def test_telegram_token(self):
        self.assertEqual(redact_text("123456789:" "ABCDEFghijklmnopqrstuvwxyz123"),
                         REDACTED)

    def test_jwt(self):
        jwt = ("eyJ" "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" "."
               "eyJ" "zdWIiOiIxMjM0NTY3ODkwIn0" "."
               "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
        self.assertEqual(redact_text(jwt), REDACTED)

    def test_bearer_inline(self):
        out = redact_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456")
        # The Authorization header consumes the whole line before _BEARER_TOKEN_RE.
        self.assertEqual(out, "Authorization: " + REDACTED)


class TestPII(unittest.TestCase):
    def test_email(self):
        self.assertEqual(redact_text("contact@example.com"), REDACTED)

    def test_iban(self):
        self.assertEqual(redact_text("FR7630006000011234567890189"), REDACTED)

    def test_phone_french(self):
        self.assertEqual(redact_text("+33 6 12 34 56 78"), REDACTED)

    def test_phone_date_not_redacted(self):
        """ISO dates (YYYY-MM-DD) must not be mistaken for a phone number."""
        self.assertEqual(redact_text("2024-01-15"), "2024-01-15")

    def test_card_luhn_valid(self):
        self.assertEqual(redact_text("4111 1111 1111 1111"), REDACTED)

    def test_card_luhn_invalid_kept(self):
        self.assertEqual(redact_text("1234567890123456"), "1234567890123456")

    def test_labeled_pii_line(self):
        self.assertEqual(redact_text("Nom complet: Jean Dupont"),
                         "Nom complet: " + REDACTED)

    def test_labeled_pii_french(self):
        self.assertEqual(redact_text("Date de naissance: 01/02/1990"),
                         "Date de naissance: " + REDACTED)


class TestSensitiveKey(unittest.TestCase):
    def test_sensitive_keys(self):
        for key in ("api_key", "access_token", "client_secret", "password",
                    "AWS_SECRET_ACCESS_KEY", "database_url", "authorization",
                    "webhook", "iban", "phone", "full_name"):
            self.assertTrue(_is_sensitive_key(key), key)

    def test_benign_keys(self):
        for key in ("token_count", "token_budget", "tokens_used", "input_tokens",
                    "max_tokens", "tokenizer", "user_name", "model", "created_at"):
            self.assertFalse(_is_sensitive_key(key), key)


class TestRedactValue(unittest.TestCase):
    def test_dict_recursive(self):
        data = {"api_key": "sk-" "abcdefghijklmnopqrstuvwxyz12345",
                "nested": {"token": "x", "ok": "texte"}}
        out = redact_value(data)
        self.assertEqual(out["api_key"], REDACTED)
        self.assertEqual(out["nested"]["token"], REDACTED)
        self.assertEqual(out["nested"]["ok"], "texte")

    def test_list_and_tuple(self):
        self.assertEqual(redact_value(["a@b.com", 1]), [REDACTED, 1])
        self.assertEqual(redact_value(("a@b.com",)), (REDACTED,))

    def test_bytes(self):
        self.assertEqual(redact_value(b"sk-" b"abcdefghijklmnopqrstuvwxyz12345"), REDACTED)

    def test_none_and_int(self):
        self.assertIsNone(redact_value(None))
        self.assertEqual(redact_value(42), 42)


class TestRobustness(unittest.TestCase):
    def test_none_input(self):
        self.assertEqual(redact_text(None), "")

    def test_idempotent(self):
        sample = ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"
                  "OPENAI_API_KEY=" "sk-" "abcdefghijklmnopqrstuvwxyz12345" "\n"
                  "contact@example.com +33 6 12 34 56 78")
        once = redact_text(sample)
        self.assertEqual(redact_text(once), once)

    def test_sanitizable_extension(self):
        self.assertEqual(_sanitizable_extension("fichier.md"), ".md")
        self.assertEqual(_sanitizable_extension("fichier.jsonl"), ".jsonl")
        self.assertEqual(_sanitizable_extension(".env"), ".env")
        self.assertEqual(_sanitizable_extension(".env.production"), ".env")
        self.assertEqual(_sanitizable_extension("fichier.bin"), ".bin")

    def test_sanitize_extensions_expected(self):
        self.assertEqual(
            SANITIZE_EXTENSIONS, {".md", ".txt", ".json", ".jsonl", ".env", ".log"}
        )


class TestRenderSanitization(unittest.TestCase):
    """Integration proof: the writing pipeline (render_md) persists
    no secret — the application point is BEFORE writing."""

    def test_message_secret_redacted_in_markdown(self):
        secret = "sk-" "abcdefghijklmnopqrstuvwxyz12345"
        conv = {
            "tool": "opencode", "id": "sess_1", "title": "Ma session",
            "project": "", "created": None, "source_path": "/fake/path",
            "source_mtime": 1.0,
            "messages": [
                {"role": "user", "text": f"mon token est {secret}", "ts": None},
                {"role": "assistant", "text": "jean@exemple.com", "ts": None},
            ],
        }
        md = render_md(conv)
        self.assertNotIn(secret, md)
        self.assertNotIn("jean@exemple.com", md)
        self.assertIn(REDACTED, md)

    def test_raw_dump_redacted(self):
        """Even the zcode raw dump (unrecognized JSON) is sanitized."""
        secret = "sk-" "abcdefghijklmnopqrstuvwxyz12345"
        conv = {
            "tool": "zcode", "id": "c1", "title": "c1", "project": "",
            "created": None, "source_path": "/fake/zcode.json",
            "source_mtime": 1.0,
            "messages": [{"role": "raw",
                          "text": f"> Format zcode non reconnu — dump brut :\n\n"
                                  f"```json\n{{\"api_key\": \"{secret}\"}}\n```",
                          "ts": None}],
        }
        md = render_md(conv)
        self.assertNotIn(secret, md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
