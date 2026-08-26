"""Identifier generation.

One place so that the id format is a single decision. Request ids are short
because they are read off a screen and typed into a search box; resource ids are
full UUIDs because they are stored.
"""

from __future__ import annotations

import uuid


def new_request_id() -> str:
    """Return a short correlation id.

    The first 12 hex characters of a UUID4. Not globally unique for all time, but
    a request id only has to be unique among the requests in flight and in the
    logs being read, and 48 bits is ample for that while staying short enough to
    read aloud.
    """
    return uuid.uuid4().hex[:12]


def new_id() -> str:
    """Return a full UUID4 string, for anything that gets persisted."""
    return str(uuid.uuid4())
