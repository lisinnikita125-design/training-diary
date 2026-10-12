"""
Бэкап базы для scheduled task на PythonAnywhere:

    python3 /home/NikitaLisin/scripts/backup_db.py

Снимок делается через sqlite3 backup API (корректен при работающем приложении,
в отличие от простого копирования файла), проверяется PRAGMA integrity_check,
сжимается в gzip и кладётся в db_backups/ рядом с репозиторием. Хранятся
последние KEEP_DEFAULT снимков.

Отдельная папка, а не backups/: там живёт ротация backup_db() из main.py
(оставляет 7 последних *.db), она удаляла бы эти файлы.

Восстановление: остановить веб-приложение (Disable на вкладке Web), затем
    gunzip -c db_backups/training_ГГГГ-ММ-ДД_ЧЧММ.db.gz > training.db
и Enable/Reload.
"""
import argparse
import gzip
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DEFAULT = os.path.join(REPO_ROOT, "training.db")
DEST_DEFAULT = os.path.join(REPO_ROOT, "db_backups")
KEEP_DEFAULT = 14
BACKUP_NAME_RE = re.compile(r"^training_\d{4}-\d{2}-\d{2}_\d{4}\.db\.gz$")


def make_snapshot(db_path, snapshot_path):
    # mode=ro: скрипт никогда не пишет в боевую базу и не создаёт её, если пути нет.
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(snapshot_path)
        try:
            src.backup(dst)
            result = dst.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dst.close()
    finally:
        src.close()
    if result != "ok":
        raise RuntimeError(f"integrity_check снимка: {result}")


def compress(snapshot_path, final_path):
    # Пишем во временный файл и переименовываем: недописанный .gz не попадёт в ротацию.
    tmp_path = final_path + ".part"
    with open(snapshot_path, "rb") as src, gzip.open(tmp_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.replace(tmp_path, final_path)


def prune(dest_dir, keep):
    backups = sorted(f for f in os.listdir(dest_dir) if BACKUP_NAME_RE.match(f))
    removed = backups[:-keep] if keep > 0 else []
    for name in removed:
        os.remove(os.path.join(dest_dir, name))
    return removed


def run_backup(db_path, dest_dir, keep, now=None):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"база не найдена: {db_path}")
    os.makedirs(dest_dir, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
    final_path = os.path.join(dest_dir, f"training_{stamp}.db.gz")
    with tempfile.TemporaryDirectory(dir=dest_dir) as tmp_dir:
        snapshot_path = os.path.join(tmp_dir, "snapshot.db")
        make_snapshot(db_path, snapshot_path)
        compress(snapshot_path, final_path)
    removed = prune(dest_dir, keep)
    return final_path, removed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Бэкап training.db")
    parser.add_argument("--db", default=DB_DEFAULT)
    parser.add_argument("--dest", default=DEST_DEFAULT)
    parser.add_argument("--keep", type=int, default=KEEP_DEFAULT)
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep должен быть не меньше 1")
    try:
        final_path, removed = run_backup(args.db, args.dest, args.keep)
    except Exception as e:
        print(f"BACKUP_FAILED {e}", file=sys.stderr)
        return 1
    size_kb = os.path.getsize(final_path) / 1024
    print(f"BACKUP_OK {final_path} {size_kb:.1f} KB, удалено старых: {len(removed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
