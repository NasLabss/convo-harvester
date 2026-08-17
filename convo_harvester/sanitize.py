# -*- coding: utf-8 -*-
"""Sanitization: redacts secrets, tokens, and PII before any writing.

This is the security core of convo-harvester: all detection regular
expressions (_PRIVATE_KEY_RE, _KNOWN_TOKEN_RE, _JWT_RE, ...) and the
redaction functions (redact_text, redact_value) live here. Their
behavior is identical to the reference module of memory-harvester
(audited 18/18): convo-harvester applies redact_text to message content
BEFORE writing .md files, so that no secret is persisted on disk.

The "existing dump migration" part of memory-harvester
(sanitize_existing_file / sanitize_existing_dumps) depends on its versioned
storage and has no place here: convo-harvester only writes brand-new
Markdown files, always sanitized.
"""

import re
from pathlib import Path

REDACTED = "[REDACTED]"
SANITIZER_POLICY_VERSION = "2.0.0"
SANITIZE_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".env",
    ".log",
}


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[^\r\n-]*PRIVATE KEY[^\r\n-]*-----.*?"
    r"(?:-----END[^\r\n-]*PRIVATE KEY[^\r\n-]*-----|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_PRIVATE_BEGIN_RE = re.compile(r"-----BEGIN[^\r\n-]*PRIVATE KEY", re.I)
_PRIVATE_END_RE = re.compile(r"-----END[^\r\n-]*PRIVATE KEY", re.I)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie)"
    r"[ \t]*:[ \t]*)[^\r\n]*$"
)
_ENV_SECRET_RE = re.compile(
    r"(?im)^([ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]*"
    r"(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|CLIENT_SECRET|"
    r"ACCESS_KEY|DATABASE_URL|CONNECTION_STRING|DSN|WEBHOOK)"
    r"[A-Z0-9_]*[ \t]*=[ \t]*)[^\r\n]+$"
)
_SECRET_LABEL = (
    r"(?:api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
    r"(?:api|client)?[ _-]?secret(?:[ _-]?key)?|private[ _-]?key|"
    r"(?:client[ _-]?)?password|passwd|authorization|"
    r"credential|credentials|account[ _-]?key|auth[ _-]?token|"
    r"cookie|session[ _-]?cookie|passport(?:[ _-]?(?:number|no))?|"
    r"iban|aws[ _-]?secret[ _-]?access[ _-]?key|database[ _-]?url|"
    r"connection[ _-]?string|dsn|signing[ _-]?key|encryption[ _-]?key|"
    r"webhook(?:[ _-]?url)?|bot[ _-]?token|cin|national[ _-]?id|"
    r"phone|telephone|mobile|mot[ _-]?de[ _-]?passe|clé[ _-]?api|cle[ _-]?api|"
    r"jeton|identifiant[ _-]?national|passeport|téléphone|cvv|cvc|"
    r"card[ _-]?(?:number|no)|numéro[ _-]?de[ _-]?carte|numero[ _-]?de[ _-]?carte|"
    r"date[_ -]?de[_ -]?naissance|birth[_ -]?date|date[_ -]?of[_ -]?birth|"
    r"adresse|address|nom[_ -]?complet|full[_ -]?name)"
)
_LABELED_QUOTED_SECRET_RE = re.compile(
    rf"(?i)([\"']?{_SECRET_LABEL}[\"']?[ \t]*[:=][ \t]*)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)
_LABELED_BARE_SECRET_RE = re.compile(
    rf"(?i)([\"']?{_SECRET_LABEL}[\"']?[ \t]*[:=][ \t]*)"
    r"([^\s,}\r\n]+)"
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:sk_(?:live|test)_[a-z0-9]{8,}|"
    r"sk-(?:live|test|ant|proj)-?[a-z0-9_-]{8,}|"
    r"sk-[a-z0-9_-]{20,}|hf_[a-z0-9]{20,}|npm_[a-z0-9]{20,}|"
    r"rk_(?:live|test)_[a-z0-9]{12,}|whsec_[a-z0-9]{12,}|"
    r"github_pat_[a-z0-9_]{20,}|"
    r"gh[pousr]_[a-z0-9]{20,}|glpat-[a-z0-9_-]{12,}|"
    r"xox[baprs]-[a-z0-9-]{10,}|AIza[0-9A-Za-z_-]{20,}|"
    r"AKIA[0-9A-Z]{16})"
)
_NPMRC_TOKEN_RE = re.compile(
    r"(?im)^([ \t]*(?://[^\s/:]+(?::\d+)?/)?_authToken"
    r"[ \t]*=[ \t]*)[^\r\n]+$"
)
_LABELED_PII_LINE_RE = re.compile(
    r"(?im)^([ \t]*(?:[-*>][ \t]*)?(?:nom[ _-]?complet|full[ _-]?name|"
    r"adresse|address|date[ _-]?de[ _-]?naissance|birth[ _-]?date|"
    r"date[ _-]?of[ _-]?birth)[ \t]*[:=][ \t]*).*$"
)
_LABELED_SECRET_LINE_RE = re.compile(
    rf"(?im)^([ \t]*(?:[-*>][ \t]*)?[\"']?{_SECRET_LABEL}[\"']?"
    r"[ \t]*[:=][ \t]*).*$"
)
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret|password)=)"
    r"[^&#\s]+"
)
_URL_USERINFO_RE = re.compile(
    r"(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|ssh|https?)://)"
    r"[^/\s:@]+:[^/\s@]+@"
)
_DISCORD_WEBHOOK_RE = re.compile(
    r"(?i)https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9._-]+"
)
_TELEGRAM_TOKEN_RE = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{20,}")
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer[ \t]+[a-z0-9._~+/=-]{8,}")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_IBAN_RE = re.compile(r"(?i)\b[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]){11,30}\b")
_PHONE_CANDIDATE_RE = re.compile(
    r"(?<!\w)(?!\d{4}-\d{2}-\d{2})(?:\+?\d[ \t().-]*){8,15}(?!\w)"
)
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_YAML_SECRET_BLOCK_RE = re.compile(
    rf"(?im)^(?P<prefix>[ \t]*[\"']?{_SECRET_LABEL}[\"']?"
    r"[ \t]*:[ \t]*[>|][-+]?[ \t]*)$"
    r"(?P<body>(?:\r?\n[ \t]+[^\r\n]*)+)"
)


def _is_sensitive_key(key):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    benign_token_metrics = {
        "tokencount",
        "tokenbudget",
        "tokensused",
        "inputtokens",
        "outputtokens",
        "maxtokens",
        "tokenlimit",
        "tokenizer",
    }
    if normalized in benign_token_metrics:
        return False
    exact = {
        "token",
        "password",
        "passwd",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "secret",
        "apikey",
        "privatekey",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "passport",
        "passportnumber",
        "iban",
        "bankaccount",
        "awssecretaccesskey",
        "databaseurl",
        "connectionstring",
        "dsn",
        "signingkey",
        "encryptionkey",
        "sessioncookie",
        "webhook",
        "webhookurl",
        "bottoken",
        "cin",
        "nationalid",
        "phone",
        "telephone",
        "mobile",
        "motdepasse",
        "cleapi",
        "clapi",
        "jeton",
        "identifiantnational",
        "passeport",
        "cvv",
        "cvc",
        "cardnumber",
        "numerodecarte",
        "dateofbirth",
        "birthdate",
        "datedenaissance",
        "address",
        "adresse",
        "fullname",
        "nomcomplet",
        "pan",
        "creditcard",
        "paymentcard",
        "card",
    }
    if normalized in exact:
        return True
    strict_fragments = (
        "secret",
        "password",
        "passwd",
        "credential",
        "privatekey",
        "apikey",
        "token",
        "cookie",
        "authheader",
        "authorization",
        "accountkey",
        "webhook",
        "bottoken",
        "signingkey",
        "encryptionkey",
    )
    if any(fragment in normalized for fragment in strict_fragments):
        return True
    return bool(
        re.search(
            r"(?:secret(?:key)?|password|passwd|credential|credentials|accountkey|"
            r"(?:api|auth|oauth|bearer|openai|anthropic|github|gitlab|access|refresh)token)$",
            normalized,
        )
        or any(
            fragment in normalized
            for fragment in (
                "apikey",
                "clientsecret",
                "privatekey",
                "passportnumber",
                "secretaccesskey",
                "databaseurl",
                "connectionstring",
                "signingkey",
                "encryptionkey",
                "sessioncookie",
                "webhook",
                "bottoken",
                "nationalid",
            )
        )
    )


def _redact_phone_candidate(match):
    value = match.group(0)
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15:
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?", value):
        return value
    separators = len(re.findall(r"[\s().-]", value))
    if value.lstrip().startswith("+") or separators >= 2 or re.fullmatch(r"0[1-9]\d{8}", value):
        return REDACTED
    return value


def _redact_card_candidate(match):
    value = match.group(0)
    digits = re.sub(r"\D", "", value)
    if not 13 <= len(digits) <= 19:
        return value
    checksum = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        checksum += number
    return REDACTED if checksum % 10 == 0 else value


def redact_text(value):
    """Redacts common structured secrets and PII without logging their value."""
    if value is None:
        return ""
    text = str(value)
    text = _PRIVATE_KEY_RE.sub(REDACTED, text)
    text = _SENSITIVE_HEADER_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _YAML_SECRET_BLOCK_RE.sub(
        lambda match: match.group("prefix") + "\n  " + REDACTED,
        text,
    )
    text = _NPMRC_TOKEN_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _LABELED_PII_LINE_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _LABELED_SECRET_LINE_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _ENV_SECRET_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _LABELED_QUOTED_SECRET_RE.sub(
        lambda match: (
            match.group(1)
            + match.group("quote")
            + REDACTED
            + match.group("quote")
        ),
        text,
    )
    text = _LABELED_BARE_SECRET_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _SECRET_QUERY_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _URL_USERINFO_RE.sub(lambda match: match.group(1) + REDACTED + "@", text)
    text = _DISCORD_WEBHOOK_RE.sub(REDACTED, text)
    text = _TELEGRAM_TOKEN_RE.sub(REDACTED, text)
    text = _KNOWN_TOKEN_RE.sub(REDACTED, text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _BEARER_TOKEN_RE.sub("Bearer " + REDACTED, text)
    text = _IBAN_RE.sub(REDACTED, text)
    text = _CARD_CANDIDATE_RE.sub(_redact_card_candidate, text)
    text = _EMAIL_RE.sub(REDACTED, text)
    text = _PHONE_CANDIDATE_RE.sub(_redact_phone_candidate, text)
    return text


def redact_value(value):
    """Recursive redaction for JSON objects and tool arguments."""
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return redact_text(value.decode("utf-8", "ignore"))
    if isinstance(value, int) and not isinstance(value, bool):
        return REDACTED if redact_text(str(value)) == REDACTED else value
    return value


def _sanitizable_extension(path):
    name = Path(path).name.lower()
    if name == ".env" or name.startswith(".env."):
        return ".env"
    return Path(path).suffix.lower()
