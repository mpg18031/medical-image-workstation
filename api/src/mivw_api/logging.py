"""Structured logging with PHI redaction.

The redaction processor is the last line of defence: a stray f-string in a log
call must not put a patient identifier into a log aggregator that has weaker
access controls than the database.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# Keys whose values are never safe to emit.
SENSITIVE_KEYS = frozenset(
    {
        "mrn",
        "mrn_enc",
        "patient_ref",
        "patientref",
        "patient_id",
        "patient_name",
        "patientname",
        "name_enc",
        "birth_date",
        "birthdate",
        "dob",
        "accession",
        "accession_number",
        "authorization",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "private_key",
        "encryption_key",
        "hmac_key",
        "original_enc",
        "deid_map",
    }
)

REDACTED = "[redacted]"

# Bearer tokens and DICOM UIDs occasionally appear inside free-text messages.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE), f"Bearer {REDACTED}"),
    (re.compile(r"\b\d+(?:\.\d+){6,}\b"), "[uid]"),
)


def redact_phi(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED

    event = event_dict.get("event")
    if isinstance(event, str):
        for pattern, replacement in _PATTERNS:
            event = pattern.sub(replacement, event)
        event_dict["event"] = event

    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level))

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # Redaction runs last before rendering so it also covers keys added
            # by earlier processors.
            redact_phi,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
