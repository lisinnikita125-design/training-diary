from conftest import count_rows, create_user, db, login

USER_TABLES = ("workout_log", "body_weight", "body_measurements", "exercises", "day_visibility")


def first_exercise(uid, day_id=1):
    conn = db()
    row = conn.execute(
        "SELECT id, name, default_weight FROM exercises WHERE user_id = ? AND day_id = ? "
        "ORDER BY sort_order LIMIT 1", (uid, day_id)).fetchone()
    conn.close()
    return row


def log_payload(exercise_id, date="2026-10-01", weight=50, reps=10):
    return {"date": date, "day_id": 1, "exercises": [
        {"exercise_id": exercise_id, "sets": [{"set_number": 1, "weight": weight, "reps": reps}]}]}


# ── Режим тренера: чужие данные ──────────────────────────────

def test_coach_can_read_own_trainee(client):
    coach = create_user("coach@example.com", is_admin=True)
    trainee = create_user("trainee@example.com", coach_id=coach)
    login(client, "coach@example.com")
    assert client.get(f"/body-weight?user_id={trainee}").status_code == 200


def test_coach_cannot_read_foreign_trainee(client):
    create_user("coach@example.com", is_admin=True)
    other_coach = create_user("other@example.com", is_admin=True)
    foreign = create_user("foreign@example.com", coach_id=other_coach)
    login(client, "coach@example.com")
    assert client.get(f"/body-weight?user_id={foreign}").status_code == 403


def test_regular_user_cannot_use_user_id_param(client):
    create_user("user@example.com")
    victim = create_user("victim@example.com")
    login(client, "user@example.com")
    assert client.get(f"/body-weight?user_id={victim}").status_code == 403


def test_data_endpoints_require_auth(client):
    for path in ("/body-weight", "/export-csv", "/last-weight/1"):
        assert client.get(path).status_code == 401, path


def test_coach_cannot_delete_foreign_user(client):
    create_user("coach@example.com", is_admin=True)
    foreign = create_user("foreign@example.com")
    login(client, "coach@example.com")
    assert client.delete(f"/admin/delete-user/{foreign}").status_code == 403
    assert count_rows("users", "id = ?", (foreign,)) == 1


# ── Удаление пользователя ────────────────────────────────────

def fill_user_data(client, email, uid):
    login(client, email)
    ex = first_exercise(uid)
    assert client.post("/log", json=log_payload(ex["id"])).status_code == 200
    assert client.post("/body-weight", json={"weight_kg": 80}).status_code == 200
    client.post("/logout")


def assert_no_user_rows(uid):
    for table in USER_TABLES:
        assert count_rows(table, "user_id = ?", (uid,)) == 0, table
    assert count_rows("coach_trainees", "trainee_id = ? OR coach_id = ?", (uid, uid)) == 0
    assert count_rows("users", "id = ?", (uid,)) == 0


def test_coach_deletes_trainee_with_all_data(client):
    coach = create_user("coach@example.com", is_admin=True)
    trainee = create_user("trainee@example.com", coach_id=coach)
    fill_user_data(client, "trainee@example.com", trainee)

    login(client, "coach@example.com")
    assert client.delete(f"/admin/delete-user/{trainee}").status_code == 200
    assert_no_user_rows(trainee)
    assert count_rows("users", "id = ?", (coach,)) == 1


def test_user_deletes_own_account_with_all_data(client):
    coach = create_user("coach@example.com", is_admin=True)
    trainee = create_user("trainee@example.com", coach_id=coach)
    fill_user_data(client, "trainee@example.com", trainee)

    login(client, "trainee@example.com")
    assert client.post("/delete-account").status_code == 200
    assert_no_user_rows(trainee)
    assert client.get("/check-auth").get_json()["auth"] is False


def test_only_admin_cannot_delete_own_account(client):
    admin = create_user("admin@example.com", is_admin=True)
    login(client, "admin@example.com")
    assert client.post("/delete-account").status_code == 400
    assert count_rows("users", "id = ?", (admin,)) == 1


# ── Запись тренировки ────────────────────────────────────────

def test_log_accepts_valid_workout(client):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)
    assert client.post("/log", json=log_payload(ex["id"])).status_code == 200
    assert count_rows("workout_log", "user_id = ? AND workout_date = ?", (uid, "2026-10-01")) == 1


def test_log_rejects_invalid_dates(client):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)
    for bad in ("2026-13-01", "2026-02-30", "2026-1-5", "01.10.2026", "", None, "2026-10-01'--"):
        resp = client.post("/log", json=log_payload(ex["id"], date=bad))
        assert resp.status_code == 400, bad
    assert count_rows("workout_log", "user_id = ?", (uid,)) == 0


def test_log_rejects_foreign_exercise(client):
    create_user("user@example.com")
    other = create_user("other@example.com")
    login(client, "user@example.com")
    foreign_ex = first_exercise(other)
    assert client.post("/log", json=log_payload(foreign_ex["id"])).status_code == 400
    assert count_rows("workout_log", "user_id = ?", (other,)) == 0


def test_log_rejects_negative_values(client):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)
    assert client.post("/log", json=log_payload(ex["id"], weight=-5)).status_code == 400
    assert client.post("/log", json=log_payload(ex["id"], reps=-1)).status_code == 400


# ── Изоляция данных ──────────────────────────────────────────

def test_last_weight_does_not_leak_other_users_data(client):
    uid = create_user("user@example.com")
    other = create_user("other@example.com")
    login(client, "other@example.com")
    other_ex = first_exercise(other)
    assert client.post("/log", json=log_payload(other_ex["id"], weight=123)).status_code == 200
    client.post("/logout")

    login(client, "user@example.com")
    own_ex = first_exercise(uid)
    assert own_ex["name"] == other_ex["name"]
    assert client.get(f"/last-weight/{own_ex['id']}").get_json()["weight"] == own_ex["default_weight"]
    # Чужое упражнение по id: ни веса из лога, ни default_weight чужой программы.
    assert client.get(f"/last-weight/{other_ex['id']}").get_json()["weight"] == 0


def test_export_csv_has_bom_and_only_own_rows(client):
    uid = create_user("user@example.com")
    other = create_user("other@example.com")
    login(client, "other@example.com")
    client.post("/log", json=log_payload(first_exercise(other)["id"], date="2026-09-15"))
    client.post("/logout")

    login(client, "user@example.com")
    client.post("/log", json=log_payload(first_exercise(uid)["id"], date="2026-10-01"))
    resp = client.get("/export-csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.get_data()
    assert body.startswith("﻿".encode("utf-8"))
    text = body.decode("utf-8")
    assert "2026-10-01" in text
    assert "2026-09-15" not in text
