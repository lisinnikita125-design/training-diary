import logging
import os
import sqlite3
from datetime import datetime

from conftest import count_rows, create_user, login
from test_data_access import first_exercise, log_payload

import db_backup
import main


def todays_backups(app_db):
    prefix = datetime.now().strftime("training_%Y-%m-%d_")
    return [n for n in db_backup.list_backups(app_db / "db_backups") if n.startswith(prefix)]


def test_first_workout_of_day_creates_backup(client, app_db):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)

    assert client.post("/log", json=log_payload(ex["id"])).status_code == 200
    assert len(todays_backups(app_db)) == 1


def test_second_workout_same_day_does_not_create_another_backup(client, app_db, monkeypatch):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)
    calls = []
    real_run_backup = db_backup.run_backup

    def counting_run_backup(*args, **kwargs):
        calls.append(args)
        return real_run_backup(*args, **kwargs)

    monkeypatch.setattr(db_backup, "run_backup", counting_run_backup)

    client.post("/log", json=log_payload(ex["id"], date="2026-10-01"))
    assert client.post("/log", json=log_payload(ex["id"], date="2026-10-02")).status_code == 200
    assert len(calls) == 1
    assert len(todays_backups(app_db)) == 1


def test_backup_once_per_day_makes_new_copy_next_day(tmp_path):
    db_path = tmp_path / "training.db"
    sqlite3.connect(db_path).close()

    first = db_backup.backup_once_per_day(str(db_path), now=datetime(2026, 10, 12, 9, 0))
    same_day = db_backup.backup_once_per_day(str(db_path), now=datetime(2026, 10, 12, 21, 30))
    next_day = db_backup.backup_once_per_day(str(db_path), now=datetime(2026, 10, 13, 8, 15))

    assert os.path.basename(first) == "training_2026-10-12_0900.db.gz"
    assert same_day is None
    assert os.path.basename(next_day) == "training_2026-10-13_0815.db.gz"
    assert db_backup.list_backups(tmp_path / "db_backups") == [
        "training_2026-10-12_0900.db.gz", "training_2026-10-13_0815.db.gz"]


def test_backup_failure_does_not_break_log(client, app_db, monkeypatch, caplog):
    uid = create_user("user@example.com")
    login(client, "user@example.com")
    ex = first_exercise(uid)

    def broken_backup(*args, **kwargs):
        raise OSError("disk quota exceeded")

    monkeypatch.setattr(db_backup, "run_backup", broken_backup)
    sent = []
    monkeypatch.setattr(main, "send_telegram", lambda message: sent.append(message))

    with caplog.at_level(logging.ERROR, logger="progressor"):
        resp = client.post("/log", json=log_payload(ex["id"]))

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert count_rows("workout_log", "user_id = ?", (uid,)) == 1
    assert any("BACKUP_ERROR" in r.getMessage() and "disk quota exceeded" in r.getMessage()
               for r in caplog.records)
    assert not os.path.exists(app_db / "db_backups") or todays_backups(app_db) == []


def test_log_does_not_touch_old_backups_folder(client, app_db):
    old_dir = app_db / "backups"
    old_dir.mkdir()
    old_names = [f"training_2026-09-{day:02d}.db" for day in range(1, 11)] + ["training_pre_demo.db"]
    for name in old_names:
        (old_dir / name).write_bytes(b"old copy")

    uid = create_user("user@example.com")
    login(client, "user@example.com")
    assert client.post("/log", json=log_payload(first_exercise(uid)["id"])).status_code == 200

    assert sorted(os.listdir(old_dir)) == sorted(old_names)
    assert all((old_dir / n).read_bytes() == b"old copy" for n in old_names)
    assert len(todays_backups(app_db)) == 1
