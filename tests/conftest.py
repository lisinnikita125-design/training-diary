import os
import sys
import tempfile
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# main.py при импорте читает config.py и сразу создаёт training.db в текущей папке.
# Подставляем тестовый config и уходим во временную папку, чтобы не задеть
# локальный config.py и базу разработчика.
_test_config = types.ModuleType("config")
_test_config.SECRET_KEY = "test-secret-key"
_test_config.APP_URL = "http://testserver"
_test_config.OWNER_EMAIL = "owner@example.com"
sys.modules["config"] = _test_config

_import_dir = tempfile.mkdtemp(prefix="progressor-import-")
_cwd = os.getcwd()
os.chdir(_import_dir)
try:
    import database  # noqa: E402
    import main  # noqa: E402
finally:
    os.chdir(_cwd)

from werkzeug.security import generate_password_hash  # noqa: E402

PASSWORD = "secret123"


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    """Чистая база в отдельной папке для каждого теста (DB_NAME относительный)."""
    monkeypatch.chdir(tmp_path)
    database.init_db()
    database.seed()
    main._login_fails.clear()
    yield tmp_path
    main._login_fails.clear()


@pytest.fixture
def client(app_db):
    main.app.config["TESTING"] = True
    with main.app.test_client() as c:
        yield c


@pytest.fixture
def make_client(app_db):
    """Несколько независимых клиентов (разные сессии) в одном тесте."""
    main.app.config["TESTING"] = True
    clients = []

    def _make():
        c = main.app.test_client()
        clients.append(c)
        return c

    yield _make


def db():
    return database.get_db()


def create_user(email, *, is_admin=False, verified=True, consents=True, coach_id=None):
    conn = db()
    consent_sql = "CURRENT_TIMESTAMP" if consents else "NULL"
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, name, is_verified, is_admin, "
        f"consent_pdn_at, consent_transfer_at) VALUES (?, ?, ?, ?, ?, {consent_sql}, {consent_sql})",
        (email, generate_password_hash(PASSWORD), email.split("@")[0], int(verified), int(is_admin)),
    )
    uid = cur.lastrowid
    if coach_id is not None:
        conn.execute("INSERT INTO coach_trainees (coach_id, trainee_id) VALUES (?, ?)", (coach_id, uid))
    conn.commit()
    conn.close()
    database.seed_user(uid)
    return uid


def login(client, email, password=PASSWORD, ip="10.0.0.1"):
    return client.post("/login", json={"email": email, "password": password},
                       headers={"X-Real-IP": ip})


def count_rows(table, where, params):
    conn = db()
    n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
    conn.close()
    return n
