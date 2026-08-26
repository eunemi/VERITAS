"""What every outbound vendor client shares: transport, retries, redaction, dates.

Two modules, both of which used to live in :mod:`app.search` and neither of which was
ever about search. :mod:`app.search.tavily` and :mod:`app.factcheck.google` have
nothing in common as APIs — one is a POST with a JSON body, the other a GET with
query parameters — and everything in common as *dependencies*: both can time out,
both can rate-limit, both can return a 200 carrying an HTML error page, both can
hand over a date string in a format their own documentation does not specify, and
neither may ever leak its API key into a log line or a response body.

This package exists so that is written once. The alternative was
``app.factcheck.google`` importing ``app.search.http``, which works and reads as a
lie: it puts an edge in the dependency graph from the fact-check package to the
web-search package, and a reader following that edge would reasonably conclude that
checking a claim against a fact-check database involves searching the web. It does
not.

The rule for what belongs here is narrow: **it must be true of an outbound HTTP
provider as such, not of any particular kind of provider.** Retry policy qualifies.
Date parsing qualifies, because the vagueness being handled is a property of vendor
documentation rather than of search. Deciding which pages are the same page does
not, and lives in :mod:`app.research`.

Nothing here imports :mod:`app.search`, :mod:`app.factcheck` or :mod:`app.research`,
and nothing here knows a vendor's name. :class:`app.providers.http.Http` carries the
one hook a family of clients needs — :attr:`~app.providers.http.Http.error`, the
:class:`~app.core.errors.ProviderError` subclass its failures are raised as — so a
search failure reaches a client as ``search_error`` and a fact-check failure as
``fact_check_error`` without this module having heard of either.
"""
