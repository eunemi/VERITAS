"""Pydantic request and response models.

Kept separate from ``app.models``, which holds SQLAlchemy tables. The two describe
different things — what crosses the wire versus what is stored — and collapsing
them couples the API contract to the schema.

**Casing.** Every field on the wire is snake_case, and no model in this package
sets an ``alias_generator``. The alternative — emitting camelCase to match
TypeScript convention — was considered and rejected: an ``alias_generator`` with
``populate_by_name`` means every field has two legal spellings, so a body can be
submitted either way, a typo in one of them silently becomes a default, and the
OpenAPI document, the log lines and the Python attribute names stop agreeing with
each other. One spelling per field is worth more than matching a convention
belonging to the other side of the wire, and generated TypeScript clients read
snake_case without complaint.
"""
