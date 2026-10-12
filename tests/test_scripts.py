import gzip
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import backup_db  # noqa: E402
import check_frontend  # noqa: E402


# ── Бэкап базы ───────────────────────────────────────────────

def make_db(path, rows=3):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(rows)])
    conn.commit()
    conn.close()


def restore(gz_path, out_path):
    with gzip.open(gz_path, "rb") as src, open(out_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    conn = sqlite3.connect(out_path)
    rows = conn.execute("SELECT v FROM t ORDER BY id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def test_backup_creates_restorable_snapshot(tmp_path):
    db_path = tmp_path / "training.db"
    make_db(db_path)
    dest = tmp_path / "db_backups"

    final_path, removed = backup_db.run_backup(str(db_path), str(dest), keep=14,
                                               now=datetime(2026, 10, 12, 3, 5))

    assert os.path.basename(final_path) == "training_2026-10-12_0305.db.gz"
    assert removed == []
    assert sorted(os.listdir(dest)) == ["training_2026-10-12_0305.db.gz"]  # без временных файлов
    assert restore(final_path, tmp_path / "restored.db") == ["row0", "row1", "row2"]


def test_backup_rotation_keeps_newest_and_ignores_foreign_files(tmp_path):
    db_path = tmp_path / "training.db"
    make_db(db_path)
    dest = tmp_path / "db_backups"
    dest.mkdir()
    (dest / "keep-me.txt").write_text("not a backup")

    start = datetime(2026, 10, 1, 3, 0)
    for day in range(5):
        backup_db.run_backup(str(db_path), str(dest), keep=3, now=start + timedelta(days=day))

    names = sorted(os.listdir(dest))
    assert names == ["keep-me.txt", "training_2026-10-03_0300.db.gz",
                     "training_2026-10-04_0300.db.gz", "training_2026-10-05_0300.db.gz"]


def test_backup_never_creates_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db.run_backup(str(tmp_path / "missing.db"), str(tmp_path / "out"), keep=3)
    assert not (tmp_path / "missing.db").exists()


def test_backup_cli_reports_failure_with_exit_code(tmp_path, capsys):
    code = backup_db.main(["--db", str(tmp_path / "missing.db"), "--dest", str(tmp_path / "out")])
    assert code == 1
    assert "BACKUP_FAILED" in capsys.readouterr().err


def test_backup_cli_success(tmp_path, capsys):
    db_path = tmp_path / "training.db"
    make_db(db_path)
    assert backup_db.main(["--db", str(db_path), "--dest", str(tmp_path / "out"), "--keep", "2"]) == 0
    assert "BACKUP_OK" in capsys.readouterr().out


# ── Проверки фронтенда ───────────────────────────────────────

GOOD_HTML = '<div id="a" style="x"><div class="b">ok</div></div><script>let a = 1;</script>'


def test_frontend_checks_pass_on_valid_html():
    assert check_frontend.run_checks(GOOD_HTML, with_node=False) == []


def test_frontend_detects_unbalanced_div():
    errors = check_frontend.run_checks(GOOD_HTML + "<div>", with_node=False)
    assert any("<div>" in e for e in errors)


def test_frontend_detects_glued_attributes():
    html = GOOD_HTML.replace('id="a" style', 'id="a"style')
    errors = check_frontend.run_checks(html, with_node=False)
    assert any("атрибуты без пробела" in e for e in errors)


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_frontend_detects_js_syntax_error():
    html = GOOD_HTML.replace("let a = 1;", "let a = ;")
    errors = check_frontend.check_js_syntax(html)
    assert any("синтаксическая ошибка" in e for e in errors)


def test_current_index_html_passes_checks():
    assert check_frontend.main() == 0
