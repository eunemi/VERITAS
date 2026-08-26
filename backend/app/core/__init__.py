"""Cross-cutting concerns: configuration, logging, errors, request context.

Nothing in this package imports from ``app.api``, ``app.services``, or the
provider seams. That one-way rule is what keeps it importable from anywhere,
including scripts and tests that never build an application.
"""
