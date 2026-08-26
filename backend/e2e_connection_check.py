"""End-to-end check of the frontend/backend contract, in process.

Drives the real ASGI application through httpx's ASGI transport: same routers,
same middleware stack, same settings loaded from backend/.env. What it does not
exercise is the socket, which uvicorn owns and this cannot reach.

Run it from anywhere:

    backend/.venv/bin/python backend/e2e_connection_check.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

import httpx

from app.core.config import get_settings
from app.main import create_app

PREFIX = get_settings().API_V1_PREFIX
ORIGINS = get_settings().CORS_ORIGINS
POLL_LIMIT = 60

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(name)


async def preflight(client: httpx.AsyncClient, origin: str) -> None:
    r = await client.options(
        f"{PREFIX}/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    allowed = r.headers.get("access-control-allow-origin")
    check(
        f"preflight {origin}",
        r.status_code == 200 and allowed == origin,
        f"{r.status_code}, allow-origin={allowed!r}",
    )


async def main() -> int:
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=120
    ) as client:
        print("\nCORS")
        for origin in ORIGINS:
            await preflight(client, origin)

        r = await client.options(
            f"{PREFIX}/auth/login",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        check(
            "preflight rejects unlisted origin",
            r.headers.get("access-control-allow-origin") is None,
            f"{r.status_code}",
        )

        r = await client.get(f"{PREFIX}/auth/login", headers={"Origin": ORIGINS[0]})
        exposed = r.headers.get("access-control-expose-headers", "")
        check(
            "expose-headers carries X-Request-ID, Location, Retry-After",
            all(
                h.lower() in exposed.lower()
                for h in ("X-Request-ID", "Location", "Retry-After")
            ),
            exposed or "(absent)",
        )

        print("\nHealth")
        for path in ("/health", f"{PREFIX}/health"):
            r = await client.get(path)
            check(f"GET {path}", r.status_code == 200, str(r.status_code))

        print("\nAuthentication")
        email = f"reader-{uuid.uuid4().hex[:8]}@example.com"
        password = "a-long-enough-password"  # noqa: S105 — a throwaway fixture

        r = await client.post(
            f"{PREFIX}/auth/register",
            json={"email": email, "password": password, "display_name": "Reader"},
            headers={"Origin": ORIGINS[0]},
        )
        check("POST /auth/register", r.status_code == 201, str(r.status_code))
        if r.status_code != 201:
            print(f"        body: {r.text[:400]}")

        r = await client.post(
            f"{PREFIX}/auth/register",
            json={"email": email, "password": password},
        )
        check(
            "duplicate registration refused", r.status_code == 422, str(r.status_code)
        )

        r = await client.post(
            f"{PREFIX}/auth/login", json={"email": email, "password": password}
        )
        check("POST /auth/login", r.status_code == 200, str(r.status_code))
        if r.status_code != 200:
            print(f"        body: {r.text[:400]}")
            return 1
        issued: dict[str, Any] = r.json()
        check(
            "login returns access_token, expires_in, user",
            {"access_token", "expires_in", "user"} <= issued.keys(),
            ", ".join(sorted(issued)),
        )
        auth = {"Authorization": f"Bearer {issued['access_token']}"}

        r = await client.post(
            f"{PREFIX}/auth/login", json={"email": email, "password": "wrong-password"}
        )
        check("wrong password refused", r.status_code == 401, str(r.status_code))

        r = await client.get(f"{PREFIX}/auth/me", headers=auth)
        check(
            "GET /auth/me",
            r.status_code == 200 and r.json().get("email") == email,
            str(r.status_code),
        )

        r = await client.get(f"{PREFIX}/auth/me")
        check(
            "GET /auth/me without token is 401",
            r.status_code == 401,
            str(r.status_code),
        )

        print("\nSubmission and polling")
        r = await client.post(
            f"{PREFIX}/verify",
            json={
                "artifact": {
                    "kind": "claim",
                    "content": "The Eiffel Tower was completed in 1889.",
                }
            },
            headers={**auth, "Origin": ORIGINS[0]},
        )
        check("POST /verify", r.status_code == 202, str(r.status_code))
        if r.status_code != 202:
            print(f"        body: {r.text[:600]}")
            return 1
        accepted = r.json()
        record_id = accepted["id"]
        location = r.headers.get("Location")
        check(
            "Location points at the record",
            location == f"{PREFIX}/verification/{record_id}",
            repr(location),
        )

        terminal: dict[str, Any] | None = None
        for attempt in range(POLL_LIMIT):
            r = await client.get(f"{PREFIX}/verification/{record_id}", headers=auth)
            if r.status_code != 200:
                check(f"poll {attempt}", False, f"{r.status_code}: {r.text[:300]}")
                return 1
            body = r.json()
            if body.get("terminal"):
                terminal = body
                break
            await asyncio.sleep(0.25)

        check(
            "polling reaches terminal",
            terminal is not None,
            f"status={terminal['status']!r}"
            if terminal
            else f"still pending after {POLL_LIMIT} polls",
        )
        if terminal is None:
            return 1

        filed = len(terminal.get("reports") or [])
        check(
            "terminal record carries a status and reports list",
            isinstance(terminal.get("reports"), list) and bool(terminal.get("status")),
            f"status={terminal['status']!r}, reports={filed}",
        )
        if terminal.get("failure"):
            print(f"        failure: {str(terminal['failure'])[:300]}")

        print("\nHistory and ownership")
        r = await client.get(f"{PREFIX}/verifications", headers=auth)
        check("GET /verifications", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            rows = r.json().get("records") or r.json().get("items") or []
            check(
                "history contains the submitted record",
                any(row.get("id") == record_id for row in rows),
                f"{len(rows)} record(s)",
            )

        r = await client.get(f"{PREFIX}/verifications")
        check(
            "GET /verifications without token is 401",
            r.status_code == 401,
            str(r.status_code),
        )

        other = f"other-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            f"{PREFIX}/auth/register", json={"email": other, "password": password}
        )
        r = await client.post(
            f"{PREFIX}/auth/login", json={"email": other, "password": password}
        )
        other_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await client.get(f"{PREFIX}/verification/{record_id}", headers=other_auth)
        check(
            "another account cannot read the record",
            r.status_code == 404,
            str(r.status_code),
        )

        r = await client.get(f"{PREFIX}/verification/{record_id}")
        check(
            "anonymous cannot read an owned record",
            r.status_code == 404,
            str(r.status_code),
        )

        r = await client.get(f"{PREFIX}/verifications", headers=other_auth)
        check(
            "a fresh account's history is empty",
            r.status_code == 200 and not (r.json().get("records") or []),
            str(r.status_code),
        )

        print("\nAnonymous submission")
        r = await client.post(
            f"{PREFIX}/verify",
            json={"artifact": {"kind": "text", "content": "A short passage to read."}},
        )
        check("POST /verify without a token", r.status_code == 202, str(r.status_code))
        if r.status_code == 202:
            anon_id = r.json()["id"]
            r = await client.get(f"{PREFIX}/verification/{anon_id}")
            check(
                "anonymous record is readable by id",
                r.status_code == 200,
                str(r.status_code),
            )

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
