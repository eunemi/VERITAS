"""The authentication endpoints, and the ownership rules they switch on.

Two halves. The first exercises register / login / me through HTTP against the real
service, the real hasher and the real in-memory store. The second is the reason this
feature exists: a verification submitted with a token belongs to that account, and
nobody else can read it or list it.

The anti-enumeration assertions are the ones worth keeping. Two of them compare whole
response bodies rather than status codes — a wrong password and an unknown address
must be indistinguishable, and so must somebody else's verification and one that was
never submitted. Both properties survive a refactor only if something checks them.

``ASGITransport`` awaits background tasks, so a ``POST /verify`` here has already run
its examination — to a failure, since no desks are built — by the time the response
is in hand. The history tests read that failed record, which is a real record.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.repositories import InMemoryUserRepository

pytestmark = pytest.mark.skipif(
    find_spec("argon2") is None or find_spec("jwt") is None,
    reason="argon2-cffi and PyJWT are needed for the authentication tests",
)

V1 = "/api/v1"
PASSWORD = "correct horse battery staple"
OTHER_PASSWORD = "a completely different passphrase"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def text_body(content: str = "The bridge opened in March.") -> dict[str, Any]:
    return {"artifact": {"kind": "text", "content": content}}


async def sign_up(
    client: AsyncClient,
    email: str = "reader@example.com",
    password: str = PASSWORD,
    **extra: Any,
) -> dict[str, Any]:
    """Register, assert it worked, and return the account."""
    response = await client.post(
        f"{V1}/auth/register",
        json={"email": email, "password": password, **extra},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def sign_in(
    client: AsyncClient,
    email: str = "reader@example.com",
    password: str = PASSWORD,
) -> str:
    """Return an access token for an existing account."""
    response = await client.post(
        f"{V1}/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["access_token"]
    return token


async def account(
    client: AsyncClient,
    email: str = "reader@example.com",
    password: str = PASSWORD,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Register and sign in, returning the account and its auth header."""
    user = await sign_up(client, email, password)
    return user, bearer(await sign_in(client, email, password))


# ---------------------------------------------------------------- register ---


async def test_registering_returns_the_account(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/auth/register",
        json={"email": "reader@example.com", "password": PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["email"] == "reader@example.com"
    assert body["created_at"]


async def test_no_token_comes_back_from_registering(client: AsyncClient) -> None:
    """Registration creates; login authenticates. One endpoint mints tokens."""
    body = await sign_up(client)

    assert "access_token" not in body


async def test_the_password_never_appears_in_a_response(client: AsyncClient) -> None:
    """Neither the password nor its hash. `UserOut` publishes four named fields."""
    response = await client.post(
        f"{V1}/auth/register",
        json={"email": "reader@example.com", "password": PASSWORD},
    )

    assert set(response.json()) == {"id", "email", "display_name", "created_at"}
    assert PASSWORD not in response.text
    assert "argon2" not in response.text


async def test_an_address_is_stored_folded_and_trimmed(client: AsyncClient) -> None:
    body = await sign_up(client, email="  Reader@Example.COM  ")

    assert body["email"] == "reader@example.com"


async def test_the_display_name_defaults_to_the_local_part(
    client: AsyncClient,
) -> None:
    body = await sign_up(client, email="reader@example.com")

    assert body["display_name"] == "reader"


async def test_a_display_name_is_kept_when_given(client: AsyncClient) -> None:
    body = await sign_up(client, display_name="A Reader")

    assert body["display_name"] == "A Reader"


async def test_a_second_registration_for_one_address_is_refused(
    client: AsyncClient,
) -> None:
    """The one place this API confirms an account exists; see the service docstring."""
    await sign_up(client)

    response = await client.post(
        f"{V1}/auth/register",
        json={"email": "reader@example.com", "password": OTHER_PASSWORD},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"] == {"email": "reader@example.com"}


async def test_case_alone_does_not_make_a_second_account(client: AsyncClient) -> None:
    """Folding happens in the domain, so the collision is caught by the same rule."""
    await sign_up(client, email="reader@example.com")

    response = await client.post(
        f"{V1}/auth/register",
        json={"email": "READER@example.com", "password": OTHER_PASSWORD},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "email", ["not-an-address", "@example.com", "reader@", "reader@localhost"]
)
async def test_something_that_is_not_an_address_is_refused(
    client: AsyncClient, email: str
) -> None:
    response = await client.post(
        f"{V1}/auth/register", json={"email": email, "password": PASSWORD}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("password", ["", "short", "x" * 129])
async def test_a_password_outside_the_bounds_is_refused(
    client: AsyncClient, password: str
) -> None:
    response = await client.post(
        f"{V1}/auth/register",
        json={"email": "reader@example.com", "password": password},
    )

    assert response.status_code == 422


async def test_an_unexpected_field_is_refused(client: AsyncClient) -> None:
    """`extra="forbid"`, so `is_active: true` in a body is a mistake, not ignored."""
    response = await client.post(
        f"{V1}/auth/register",
        json={
            "email": "reader@example.com",
            "password": PASSWORD,
            "is_active": True,
        },
    )

    assert response.status_code == 422


# ------------------------------------------------------------------- login ---


async def test_signing_in_returns_a_token_and_the_account(
    client: AsyncClient,
) -> None:
    user = await sign_up(client)

    response = await client.post(
        f"{V1}/auth/login",
        json={"email": "reader@example.com", "password": PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    # The account rides along so a client need not follow with GET /auth/me.
    assert body["user"] == user


async def test_signing_in_is_case_insensitive_on_the_address(
    client: AsyncClient,
) -> None:
    await sign_up(client, email="reader@example.com")

    response = await client.post(
        f"{V1}/auth/login",
        json={"email": "Reader@Example.com", "password": PASSWORD},
    )

    assert response.status_code == 200


async def test_the_wrong_password_is_refused(client: AsyncClient) -> None:
    await sign_up(client)

    response = await client.post(
        f"{V1}/auth/login",
        json={"email": "reader@example.com", "password": OTHER_PASSWORD},
    )

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "authentication_failed"
    assert error["message"] == "Email or password is incorrect."


async def test_an_unknown_address_is_refused_identically(client: AsyncClient) -> None:
    """The anti-enumeration property, asserted on the whole body.

    A different message, code or status for "no such account" would answer the
    question an attacker holding a list of addresses is actually asking. Only the
    request id differs, and that is per-request rather than per-outcome.
    """
    await sign_up(client)

    wrong_password = await client.post(
        f"{V1}/auth/login",
        json={"email": "reader@example.com", "password": OTHER_PASSWORD},
    )
    no_account = await client.post(
        f"{V1}/auth/login",
        json={"email": "nobody@example.com", "password": OTHER_PASSWORD},
    )

    assert wrong_password.status_code == no_account.status_code == 401
    assert _without_request_id(wrong_password.json()) == _without_request_id(
        no_account.json()
    )


async def test_a_malformed_address_is_a_401_not_a_422(client: AsyncClient) -> None:
    """Login has one failure shape. A 422 here would separate format from credential."""
    response = await client.post(
        f"{V1}/auth/login", json={"email": "not-an-address", "password": PASSWORD}
    )

    assert response.status_code == 401


async def test_a_closed_account_is_refused_identically(
    app: FastAPI, client: AsyncClient
) -> None:
    user = await sign_up(client)
    await _deactivate(app, user["id"])

    response = await client.post(
        f"{V1}/auth/login",
        json={"email": "reader@example.com", "password": PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email or password is incorrect."


async def test_login_has_no_password_floor(client: AsyncClient) -> None:
    """A minimum here would tell a caller their password predates today's rule.

    Short is a rejected credential, not a rejected body — so 401, not 422.
    """
    response = await client.post(
        f"{V1}/auth/login", json={"email": "reader@example.com", "password": "x"}
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------- me ---


async def test_me_returns_the_signed_in_account(client: AsyncClient) -> None:
    user, headers = await account(client)

    response = await client.get(f"{V1}/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == user


async def test_me_without_a_token_is_401(client: AsyncClient) -> None:
    response = await client.get(f"{V1}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic cmVhZGVyOnB3"},
        {"Authorization": "some-token"},
    ],
)
async def test_me_refuses_anything_that_is_not_a_valid_bearer_token(
    client: AsyncClient, header: dict[str, str]
) -> None:
    response = await client.get(f"{V1}/auth/me", headers=header)

    assert response.status_code == 401


async def test_an_auth_failure_uses_the_error_envelope(client: AsyncClient) -> None:
    """Not FastAPI's `{"detail": ...}`, which is why `auto_error=False` is set."""
    response = await client.get(f"{V1}/auth/me")

    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}


async def test_deactivating_an_account_invalidates_its_live_token(
    app: FastAPI, client: AsyncClient
) -> None:
    """The reason the account is re-read on every request instead of trusted.

    The token is still perfectly valid — correctly signed, unexpired — and it stops
    working the moment the account does, rather than at the end of its lifetime.
    """
    user, headers = await account(client)
    assert (await client.get(f"{V1}/auth/me", headers=headers)).status_code == 200

    await _deactivate(app, user["id"])

    assert (await client.get(f"{V1}/auth/me", headers=headers)).status_code == 401


async def test_a_token_for_an_account_that_is_gone_is_refused(
    app: FastAPI, client: AsyncClient
) -> None:
    """Swapping the store empties it, which is what a deleted row looks like here."""
    _user, headers = await account(client)
    app.state.user_repository = InMemoryUserRepository()

    assert (await client.get(f"{V1}/auth/me", headers=headers)).status_code == 401


# --------------------------------------------------------------- ownership ---


async def test_submitting_with_a_token_puts_the_record_in_your_history(
    client: AsyncClient,
) -> None:
    _user, headers = await account(client)

    submitted = await client.post(f"{V1}/verify", json=text_body(), headers=headers)
    history = await client.get(f"{V1}/verifications", headers=headers)

    assert submitted.status_code == 202
    body = history.json()
    assert body["count"] == 1
    assert [row["id"] for row in body["items"]] == [submitted.json()["id"]]


async def test_submitting_without_a_token_still_works(client: AsyncClient) -> None:
    """Anonymous submission is a supported case: the owner column is nullable."""
    response = await client.post(f"{V1}/verify", json=text_body())

    assert response.status_code == 202


async def test_an_anonymous_record_stays_readable_by_id(client: AsyncClient) -> None:
    """With no owner there is nobody to withhold it from, and its id is the handle."""
    submitted = await client.post(f"{V1}/verify", json=text_body())

    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    assert response.status_code == 200


async def test_an_anonymous_record_is_in_nobody_s_history(
    client: AsyncClient,
) -> None:
    _user, headers = await account(client)
    await client.post(f"{V1}/verify", json=text_body())

    history = await client.get(f"{V1}/verifications", headers=headers)

    assert history.json() == {"items": [], "count": 0}


async def test_the_owner_can_read_their_own_record(client: AsyncClient) -> None:
    _user, headers = await account(client)
    submitted = await client.post(f"{V1}/verify", json=text_body(), headers=headers)

    response = await client.get(
        f"{V1}/verification/{submitted.json()['id']}", headers=headers
    )

    assert response.status_code == 200


async def test_somebody_else_s_record_is_404_and_not_403(client: AsyncClient) -> None:
    """A 403 would confirm the id exists, which is the enumeration this closes.

    The body is compared against a genuinely unknown id, because a distinguishable
    404 leaks exactly what the status code was chosen to hide.
    """
    _owner, owner_headers = await account(client, "owner@example.com")
    _other, other_headers = await account(client, "other@example.com", OTHER_PASSWORD)
    submitted = await client.post(
        f"{V1}/verify", json=text_body(), headers=owner_headers
    )
    record_id = submitted.json()["id"]

    denied = await client.get(
        f"{V1}/verification/{record_id}", headers=other_headers
    )
    absent = await client.get(f"{V1}/verification/nope", headers=other_headers)

    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == absent.json()["error"]["code"]
    assert denied.json()["error"]["message"].replace(record_id, "X") == absent.json()[
        "error"
    ]["message"].replace("nope", "X")


async def test_an_owned_record_is_not_readable_anonymously(
    client: AsyncClient,
) -> None:
    _owner, headers = await account(client)
    submitted = await client.post(f"{V1}/verify", json=text_body(), headers=headers)

    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    assert response.status_code == 404


async def test_a_rejected_token_is_not_treated_as_anonymous(
    client: AsyncClient,
) -> None:
    """On a route where authentication is optional, a *bad* token is still a 401.

    Reading it as anonymous would silently drop ownership: an expired session would
    go on submitting records its owner could never list.
    """
    response = await client.post(
        f"{V1}/verify", json=text_body(), headers=bearer("not-a-token")
    )

    assert response.status_code == 401


# ----------------------------------------------------------------- history ---


async def test_history_requires_a_token(client: AsyncClient) -> None:
    """There is no anonymous history: an anonymous record has no owner to match."""
    response = await client.get(f"{V1}/verifications")

    assert response.status_code == 401


async def test_history_holds_only_your_own_records(client: AsyncClient) -> None:
    _owner, owner_headers = await account(client, "owner@example.com")
    _other, other_headers = await account(client, "other@example.com", OTHER_PASSWORD)
    mine = await client.post(f"{V1}/verify", json=text_body(), headers=owner_headers)
    await client.post(f"{V1}/verify", json=text_body(), headers=other_headers)

    history = await client.get(f"{V1}/verifications", headers=owner_headers)

    body = history.json()
    assert [row["id"] for row in body["items"]] == [mine.json()["id"]]


async def test_history_is_newest_first(client: AsyncClient) -> None:
    _user, headers = await account(client)
    first = await client.post(f"{V1}/verify", json=text_body("one"), headers=headers)
    second = await client.post(f"{V1}/verify", json=text_body("two"), headers=headers)

    history = await client.get(f"{V1}/verifications", headers=headers)

    assert [row["id"] for row in history.json()["items"]] == [
        second.json()["id"],
        first.json()["id"],
    ]


async def test_a_history_row_carries_no_reports(client: AsyncClient) -> None:
    """A summary, not the record: twenty full records is a response nobody asked for."""
    _user, headers = await account(client)
    await client.post(f"{V1}/verify", json=text_body(), headers=headers)

    history = await client.get(f"{V1}/verifications", headers=headers)

    row = history.json()["items"][0]
    assert "reports" not in row
    assert row["status"] == "failed"
    assert row["terminal"] is True


async def test_history_can_be_shortened(client: AsyncClient) -> None:
    _user, headers = await account(client)
    for _ in range(3):
        await client.post(f"{V1}/verify", json=text_body(), headers=headers)

    history = await client.get(f"{V1}/verifications?limit=2", headers=headers)

    assert history.json()["count"] == 2


@pytest.mark.parametrize("limit", ["0", "-1", "101", "all"])
async def test_a_limit_outside_the_bounds_is_refused(
    client: AsyncClient, limit: str
) -> None:
    _user, headers = await account(client)

    response = await client.get(f"{V1}/verifications?limit={limit}", headers=headers)

    assert response.status_code == 422


# ----------------------------------------------------------------- helpers ---


async def _deactivate(app: FastAPI, user_id: str) -> None:
    """Close an account behind the API's back, as an admin path eventually would."""
    store = app.state.user_repository
    user = await store.get(user_id)
    assert user is not None
    await store.update(user.deactivated())


def _without_request_id(body: dict[str, Any]) -> dict[str, Any]:
    """Drop the per-request correlation id, which differs between any two calls."""
    return {k: v for k, v in body["error"].items() if k != "request_id"}
