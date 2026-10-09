"""Reading a date out of whatever a provider actually sent.

Three APIs, four documented formats, no shared convention, and not one of them
guarantees a date is present at all:

============================  ==============================  ==================
provider / field              documented example              basis
============================  ==============================  ==================
Tavily ``published_date``     ``Tue, 11 Mar 2025 17:00:00 GMT``  RFC 1123
Serper ``date``               ``Mar 10, 2022``                display
Brave ``page_age``            ISO 8601, format unspecified    ISO
Brave ``age``                 ``2 days ago``                  relative
============================  ==============================  ==================

None of those formats is *specified* by its vendor. Tavily's appears once, in a
tutorial, and is absent from the OpenAPI schema entirely. Brave's ``page_age`` has
no documented format, pattern or example. Serper's ``date`` has one example and no
statement of whether a relative string can appear there instead. So this module is
built to be wrong about a format without being wrong about a date: every parser
is tried against every string regardless of which field it came from, and anything
that does not parse yields ``None`` rather than a guess.

That last point is the whole design. A parser that returns ``None`` costs a source
its date, which is visible and recoverable — :func:`app.research.urls.date_from_path`
may still find one, and either way
:attr:`~app.domain.research.Source.date_text` keeps the original string so the gap
can be diagnosed. A parser that returns a *plausible wrong answer* puts a date on
a source that its publisher never stated, and nothing downstream can detect it.
Given a string it does not understand, this module has nothing to say.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from app.domain import DateBasis

__all__ = ["parse_absolute", "parse_relative", "resolve"]

#: Formats tried after :meth:`datetime.fromisoformat` and RFC 1123 have both
#: declined. Display forms, in the order a Google-derived string is most likely to
#: use them.
_DISPLAY_FORMATS: tuple[str, ...] = (
    "%b %d, %Y",  # Mar 10, 2022      — the one documented Serper example
    "%B %d, %Y",  # March 10, 2022
    "%d %b %Y",  # 10 Mar 2022
    "%d %B %Y",  # 10 March 2022
    "%b %d %Y",  # Mar 10 2022
    "%Y/%m/%d",  # 2022/03/10
    "%d/%m/%Y",  # 10/03/2022        — see the note in `parse_absolute`
)

#: ``"2 days ago"``, ``"about 3 hours ago"``, ``"1 month ago"``. The trailing
#: ``ago`` is required: without it, ``"2 days"`` is a duration and not a date.
_RELATIVE = re.compile(
    r"^\s*(?:about\s+|around\s+|~\s*)?"
    r"(?P<count>\d{1,4})\s*"
    r"(?P<unit>second|sec|minute|min|hour|hr|day|week|month|year)s?"
    r"\s+ago\s*$",
    re.IGNORECASE,
)

#: Seconds per unit. ``month`` and ``year`` are approximations, and the reason
#: that is acceptable is that they are only ever used for ordering: a relative age
#: is recorded as :attr:`~app.domain.research.DateBasis.PROVIDER_RELATIVE`, and a
#: consumer displaying such a date is directed to
#: :attr:`~app.domain.research.Source.date_text` — the provider's own "3 months
#: ago", which is both what it said and all it knew.
_UNITS: dict[str, timedelta] = {
    "second": timedelta(seconds=1),
    "sec": timedelta(seconds=1),
    "minute": timedelta(minutes=1),
    "min": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "hr": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "year": timedelta(days=365),
}

#: Bare words that stand in for a small relative age.
_WORDS: dict[str, timedelta] = {
    "just now": timedelta(0),
    "moments ago": timedelta(0),
    "today": timedelta(0),
    "yesterday": timedelta(days=1),
}

#: Nothing before this is a publication date on the web. Guards against a parse
#: that succeeds on a string that was never a date — ``"12/25"`` read as year 12,
#: or an id that happens to fit a format.
_EARLIEST = datetime(1990, 1, 1, tzinfo=UTC)


def parse_absolute(text: str) -> datetime | None:
    """An absolute date from ``text``, as an aware UTC datetime, or ``None``.

    Tries ISO 8601, then RFC 1123, then the display forms in
    :data:`_DISPLAY_FORMATS`. A naive result is read as UTC — the alternative
    would be to read it as the server's local time, which would make the same
    response parse differently on two machines.

    Ambiguity is resolved by refusing to resolve it: ``%m/%d/%Y`` is absent from
    the format list even though it is common, because ``03/10/2022`` is March in
    the United States and October almost everywhere else and no provider here
    documents a locale. ``%d/%m/%Y`` is present and tried last, so a string like
    ``25/12/2022`` — unambiguous, since there is no 25th month — still parses,
    while ``03/10/2022`` lands on 3 October. A caller that needs certainty has
    ``date_text``.
    """
    text = text.strip()
    if not text:
        return None

    # `fromisoformat` in 3.11+ accepts a trailing Z and most 8601 spellings.
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        pass

    # RFC 1123 / HTTP-date, which is what Tavily's one documented example is.
    try:
        return _as_utc(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        pass

    for fmt in _DISPLAY_FORMATS:
        try:
            return _as_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue

    return None


def parse_relative(text: str, *, now: datetime) -> datetime | None:
    """A relative age — ``"2 days ago"`` — resolved against ``now``, or ``None``.

    ``now`` is passed in rather than read from the clock so that the same response
    resolves to the same date twice, and so a test can assert an exact value. It
    should be :attr:`~app.domain.research.Dossier.retrieved_at`: the age is
    relative to the moment the provider answered, not to the moment a reader looks
    at the dossier.
    """
    text = text.strip()
    if not text:
        return None

    if (word := _WORDS.get(text.casefold())) is not None:
        return _as_utc(now) - word

    match = _RELATIVE.match(text)
    if not match:
        return None
    unit = _UNITS.get(match.group("unit").lower())
    if unit is None:
        return None
    return _as_utc(now) - unit * int(match.group("count"))


def resolve(
    text: str | None,
    *,
    now: datetime,
    basis: DateBasis,
) -> tuple[datetime, DateBasis] | None:
    """Turn one provider date string into a date and the basis to record for it.

    ``basis`` is what the *field* claims to be — :attr:`DateBasis.PROVIDER` for
    Tavily's ``published_date``, :attr:`DateBasis.PROVIDER_MODIFIED` for Brave's
    ``page_age`` — and it is honoured only when the string turns out to be an
    absolute date. A field documented as absolute that arrives holding ``"3 days
    ago"`` is recorded as :attr:`DateBasis.PROVIDER_RELATIVE`, because that is
    what it is. Serper's docs never say whether its ``date`` can be relative, so
    this is not a hypothetical branch; it is the only way to be right either way.

    ``None`` for a missing, blank or unparseable string. The caller keeps ``text``
    on the source regardless, so an unparseable format shows up as a source with
    ``date_text`` and no ``published_at`` — which is a legible bug report rather
    than a silent loss.
    """
    if text is None:
        return None
    if (found := parse_absolute(text)) is not None:
        return (found, basis) if _plausible(found, now) else None
    if (found := parse_relative(text, now=now)) is not None:
        return (found, DateBasis.PROVIDER_RELATIVE) if _plausible(found, now) else None
    return None


def _plausible(found: datetime, now: datetime) -> bool:
    """Inside the range a web publication date can occupy.

    A date after ``now`` is not a publication date the provider observed, and a
    date before the web existed is a misparse. Both are rejected rather than
    clamped: a clamped date is a fabricated one.

    One day of slack on the upper bound, because clock skew between a provider and
    this host is real and an article published minutes ago should not lose its
    date to it.
    """
    return _EARLIEST <= found <= _as_utc(now) + timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    """Aware UTC, reading a naive value as UTC rather than as local time.

    Everything downstream compares against
    :attr:`~app.domain.research.Dossier.retrieved_at`, which is aware, and mixing
    the two raises. Reading naive input as UTC is a documented assumption; reading
    it as local time would make the parse depend on where the process runs.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
