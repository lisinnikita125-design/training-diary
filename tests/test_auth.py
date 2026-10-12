from conftest import PASSWORD, count_rows, create_user, db, login

import main


def register_payload(email="new@example.com", invite=None, **overrides):
    payload = {"email": email, "password": PASSWORD, "name": "New",
               "consent_pdn": True, "consent_transfer": True}
    if invite is not None:
        payload["invite"] = invite
    payload.update(overrides)
    return payload


def create_invite(client, admin_email):
    assert login(client, admin_email).status_code == 200
    resp = client.post("/admin/invite")
    assert resp.status_code == 200
    return resp.get_json()["invite_url"].split("invite=")[1]


# ── Регистрация ──────────────────────────────────────────────

def test_register_without_invite_is_rejected(client):
    resp = client.post("/register", json=register_payload())
    assert resp.status_code == 400
    assert "приглашению" in resp.get_json()["message"]
    assert count_rows("users", "email = ?", ("new@example.com",)) == 0


def test_register_with_unknown_invite_is_rejected(client):
    resp = client.post("/register", json=register_payload(invite="no-such-code"))
    assert resp.status_code == 400
    assert count_rows("users", "email = ?", ("new@example.com",)) == 0


def test_register_without_invite_does_not_reveal_existing_email(client):
    create_user("taken@example.com")
    resp = client.post("/register", json=register_payload(email="taken@example.com"))
    assert resp.status_code == 400  # не 409: без приглашения нельзя проверить, занят ли email


def test_register_requires_both_consents(make_client):
    create_user("coach@example.com", is_admin=True)
    code = create_invite(make_client(), "coach@example.com")
    guest = make_client()
    for overrides in ({"consent_pdn": False}, {"consent_transfer": False},
                      {"consent_pdn": "true"}, {"consent_transfer": None}):
        resp = guest.post("/register", json=register_payload(invite=code, **overrides))
        assert resp.status_code == 400, overrides
    assert count_rows("users", "email = ?", ("new@example.com",)) == 0


def test_register_with_invite_links_trainee_and_consumes_invite(make_client):
    coach_id = create_user("coach@example.com", is_admin=True)
    code = create_invite(make_client(), "coach@example.com")

    resp = make_client().post("/register", json=register_payload(invite=code))
    assert resp.status_code == 200

    conn = db()
    user = conn.execute(
        "SELECT id, is_admin, consent_pdn_at, consent_transfer_at FROM users WHERE email = ?",
        ("new@example.com",)).fetchone()
    invite = conn.execute("SELECT used_at, used_by FROM coach_invites WHERE code = ?", (code,)).fetchone()
    conn.close()
    assert user["is_admin"] == 0
    assert user["consent_pdn_at"] is not None and user["consent_transfer_at"] is not None
    assert invite["used_at"] is not None and invite["used_by"] == user["id"]
    assert count_rows("coach_trainees", "coach_id = ? AND trainee_id = ?", (coach_id, user["id"])) == 1
    assert count_rows("exercises", "user_id = ?", (user["id"],)) > 0


def test_invite_cannot_be_used_twice(make_client):
    create_user("coach@example.com", is_admin=True)
    code = create_invite(make_client(), "coach@example.com")
    assert make_client().post("/register", json=register_payload(invite=code)).status_code == 200

    resp = make_client().post("/register", json=register_payload(email="second@example.com", invite=code))
    assert resp.status_code == 400
    assert count_rows("users", "email = ?", ("second@example.com",)) == 0


def test_non_admin_cannot_create_invite(client):
    create_user("user@example.com")
    login(client, "user@example.com")
    assert client.post("/admin/invite").status_code == 403


# ── Вход ─────────────────────────────────────────────────────

def test_login_success_and_wrong_password(client):
    create_user("user@example.com")
    assert login(client, "user@example.com", "wrong-pass").status_code == 401
    assert login(client, "user@example.com").status_code == 200
    assert client.get("/check-auth").get_json()["auth"] is True


def test_login_unverified_user_is_rejected(client):
    create_user("user@example.com", verified=False)
    assert login(client, "user@example.com").status_code == 403


def test_login_locks_after_max_failures(client):
    create_user("user@example.com")
    for _ in range(main.LOGIN_MAX_FAILS):
        assert login(client, "user@example.com", "wrong-pass").status_code == 401
    assert login(client, "user@example.com", "wrong-pass").status_code == 429
    # Верный пароль во время блокировки тоже не пускает.
    assert login(client, "user@example.com").status_code == 429


def test_login_lock_is_per_ip_and_email(client):
    create_user("user@example.com")
    for _ in range(main.LOGIN_MAX_FAILS):
        login(client, "user@example.com", "wrong-pass", ip="10.0.0.1")
    assert login(client, "user@example.com", ip="10.0.0.2").status_code == 200


def test_successful_login_resets_failure_counter(client):
    create_user("user@example.com")
    for _ in range(main.LOGIN_MAX_FAILS - 1):
        login(client, "user@example.com", "wrong-pass")
    assert login(client, "user@example.com").status_code == 200
    for _ in range(main.LOGIN_MAX_FAILS - 1):
        assert login(client, "user@example.com", "wrong-pass").status_code == 401


# ── Согласия ─────────────────────────────────────────────────

def test_user_without_consents_gets_needs_consent_until_given(client):
    create_user("old@example.com", consents=False)
    login(client, "old@example.com")
    assert client.get("/check-auth").get_json()["needs_consent"] is True

    assert client.post("/consent", json={"consent_pdn": True}).status_code == 400
    assert client.get("/check-auth").get_json()["needs_consent"] is True

    resp = client.post("/consent", json={"consent_pdn": True, "consent_transfer": True})
    assert resp.status_code == 200
    assert client.get("/check-auth").get_json()["needs_consent"] is False


def test_consent_requires_auth(client):
    resp = client.post("/consent", json={"consent_pdn": True, "consent_transfer": True})
    assert resp.status_code == 401


def test_privacy_page_is_served(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "Политика обработки персональных данных" in resp.get_data(as_text=True)
