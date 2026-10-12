"""
Бэкап training.db: снимок через sqlite3 backup API (корректен при работающем
приложении, в отличие от простого копирования файла), проверка
PRAGMA integrity_check, gzip в db_backups/, хранятся последние KEEP_DEFAULT копий.

Используется в двух местах:
- main.py вызывает backup_once_per_day() после записи тренировки (/log);
- scripts/backup_db.py — ручной запуск из консоли.

Папка отдельная от backups/: там лежит training_pre_demo.db для восстановления
после демо-режима, этот модуль backups/ не трогает.

Восстановление: остановить веб-приложение (Disable на вкладке Web), затем
    gunzip -c db_backups/training_ГГГГ-ММ-ДД_ЧЧММ.db.gz > training.db
и Enable.
"""
import gzip
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime

BACKUP_DIR_NAME = "db_backups"
KEEP_DEFAULT = 14
BACKUP_NAME_RE = re.compile(r"^training_\d{4}-\d{2}-\d{2}_\d{4}\.db\.gz$")


def make_snapshot(db_path, snapshot_path):
    # mode=ro: бэкап никогда не пишет в боевую базу и не создаёт её, если пути нет.
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


def list_backups(dest_dir):
    if not os.path.isdir(dest_dir):
        return []
    return sorted(f for f in os.listdir(dest_dir) if BACKUP_NAME_RE.match(f))


def prune(dest_dir, keep):
    backups = list_backups(dest_dir)
    removed = backups[:-keep] if keep > 0 else []
    for name in removed:
        os.remove(os.path.join(dest_dir, name))
    return removed


def run_backup(db_path, dest_dir, keep=KEEP_DEFAULT, now=None):
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


def backup_once_per_day(db_path, keep=KEEP_DEFAULT, now=None):
    """
    Делает бэкап в db_backups/ рядом с базой, если за сегодня его ещё нет.
    Возвращает путь к новому файлу или None, если сегодняшний уже есть.
    """
    now = now or datetime.now()
    dest_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), BACKUP_DIR_NAME)
    today_prefix = now.strftime("training_%Y-%m-%d_")
    if any(name.startswith(today_prefix) for name in list_backups(dest_dir)):
        return None
    final_path, _ = run_backup(db_path, dest_dir, keep, now)
    return final_path
