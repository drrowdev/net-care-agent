"""Caregiver date entry: Finnish or ISO text in, stored ISO text out.

The record *shows* Finnish dates everywhere — ``14.8.2026``, ``8/2026``,
``2026`` — so the caregiver has to be able to type them too.  Nothing about
storage changes here: a date is still kept as the same ISO string, at exactly
the precision that was entered.

This module is deliberately separate from :func:`agent.schema.derive_date_precision`.
That function classifies values that are *already stored*, and it is also
mirrored in the browser to check server responses.  Loosening it would let
typed text reach the profile and would break those checks.  The flow is always:

    typed text -> this module -> stored ISO text -> derive_date_precision

The grammar is small and strict on purpose.  A clinical record is far worse off
with a date that was silently misread than with one that was refused, so
anything outside the accepted forms is rejected rather than guessed at.

Accepted, after trimming surrounding whitespace:

===========================  ==============  ===========
typed                        stored          precision
===========================  ==============  ===========
``14.8.2026`` ``04.08.2026``  ``2026-08-14``  day
``14.8.2026.``               ``2026-08-14``  day
``8/2026`` ``08/2026``       ``2026-08``     month
``2026``                     ``2026``        year
===========================  ==============  ===========

The ISO forms the caregiver already knows keep working exactly as before, so
nothing he has learned stops working.  They are simply no longer advertised.

Everything else is refused, including ``14/8/2026`` and ``2026.8.14`` (the
day/month order cannot be trusted), ``14.8.26`` (a two-digit year), impossible
calendar dates such as ``31.2.2026``, and dates spelt with anything other than
plain digits.  ``static/app.js`` implements the same grammar for the browser
and ``tests/test_finnish_date_input.py`` proves the two agree case by case.
"""

from __future__ import annotations

import datetime
import re

# Plain-English wording for a refused date. It says what may be typed and
# names no field and no machine notation, because the caregiver reads it.
DATE_INPUT_HELP = "Enter the date as 14.8.2026, 8/2026 or 2026."
OPTIONAL_DATE_INPUT_HELP = "Enter the date as 14.8.2026, 8/2026 or 2026, or leave it empty."
FULL_DATE_INPUT_HELP = "Enter the full date as 14.8.2026."
OPTIONAL_FULL_DATE_INPUT_HELP = "Enter the full date as 14.8.2026, or leave it empty."

# ``[0-9]`` rather than ``\d``: Python's ``\d`` also matches Arabic-Indic and
# full-width digits, which ``int()`` would then happily convert.
_FINNISH_DAY = re.compile(r"^([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})\.?$")
_FINNISH_MONTH = re.compile(r"^([0-9]{1,2})/([0-9]{4})$")
_ISO_DAY = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_ISO_MONTH = re.compile(r"^([0-9]{4})-([0-9]{2})$")
_YEAR = re.compile(r"^([0-9]{4})$")


class DateInputError(ValueError):
    """A typed date that is not one of the accepted forms."""


def _day(year: int, month: int, day: int) -> tuple[str, str] | None:
    try:
        # Rejects month 13, 31 February, and 29 February outside a leap year.
        return datetime.date(year, month, day).isoformat(), "day"
    except ValueError:
        return None


def _month(year: int, month: int) -> tuple[str, str] | None:
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}", "month"


def read_date_input(value: object) -> tuple[str, str] | None:
    """Return ``(stored ISO text, precision)``, or ``None`` if unreadable.

    ``None`` means "this is not a date I accept" — including empty text and
    values that are not text at all.  Callers decide separately whether an
    absent date is allowed; this function never treats junk as absence.
    """
    if not isinstance(value, str):
        return None
    # Trimmed against an explicit ASCII set rather than str.strip()/String.trim,
    # whose whitespace definitions differ (byte-order mark, NEL), so the browser
    # and the server read exactly the same set of strings.
    text = value.strip(" \t\n\r\f\v")
    if not text:
        return None
    if match := _FINNISH_DAY.match(text):
        return _day(int(match[3]), int(match[2]), int(match[1]))
    if match := _ISO_DAY.match(text):
        return _day(int(match[1]), int(match[2]), int(match[3]))
    if match := _FINNISH_MONTH.match(text):
        return _month(int(match[2]), int(match[1]))
    if match := _ISO_MONTH.match(text):
        return _month(int(match[1]), int(match[2]))
    if match := _YEAR.match(text):
        return (match[1], "year") if int(match[1]) >= 1 else None
    return None


def parse_partial_date(value: object, *, optional: bool = False) -> str:
    """Stored ISO text at whatever precision was typed.

    Nothing is filled in: a year stays a year and a month stays a month.

    ``optional`` only chooses the wording shown when the date cannot be read;
    it never makes an empty box acceptable.  Callers that allow an absent date
    check for that themselves before calling, so junk is never mistaken for
    absence.
    """
    read = read_date_input(value)
    if read is None:
        raise DateInputError(OPTIONAL_DATE_INPUT_HELP if optional else DATE_INPUT_HELP)
    return read[0]


def parse_full_date(value: object, *, optional: bool = False) -> str:
    """Stored ISO text for a complete day, for the fields that need one.

    ``optional`` only chooses the wording, exactly as in
    :func:`parse_partial_date`.
    """
    read = read_date_input(value)
    if read is None or read[1] != "day":
        raise DateInputError(OPTIONAL_FULL_DATE_INPUT_HELP if optional else FULL_DATE_INPUT_HELP)
    return read[0]
