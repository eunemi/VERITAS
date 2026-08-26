"""Version 1 router.

Every v1 route module is included here, and this is the only router
:func:`app.main.create_app` mounts under ``/api/v1``. Adding an endpoint is one
import and one ``include_router`` line in this file — routes never reach the
application factory directly.

A version 2, when there is one, is a sibling package with its own router. The
prefix lives in configuration, not in the route decorators, so nothing has to be
edited inside a route to move it.

Shared error responses are declared on each route module's ``APIRouter``
(``responses=COMMON_ERRORS``) rather than on this one. Health is included here *and*
mounted unversioned by the application factory, so anything declared at this level
would appear on one mount of ``/health`` and not the other — and a liveness check
that documents a 422 it cannot produce is worse than a small repetition.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import auth, claims, health, research, verification

router = APIRouter()

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(verification.router)
router.include_router(claims.router)
router.include_router(research.router)
