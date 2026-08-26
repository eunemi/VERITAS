"""Getting a submitted artifact off the network.

One module, :mod:`app.media.fetch`, shared by every desk that reads a file rather
than a string. It lives outside :mod:`app.vision` and :mod:`app.audio` because the
request-forgery guard inside it is the sort of code that must exist exactly once —
a second copy is a second thing to remember to fix.

Nothing is re-exported here. Callers do ``from app.media import fetch`` and then
``fetch.fetch(...)``, so a test can substitute the module attribute.
"""

from __future__ import annotations
