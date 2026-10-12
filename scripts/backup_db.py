"""
Ручной бэкап базы из консоли PythonAnywhere:

    python3 /home/NikitaLisin/scripts/backup_db.py

Сама логика — в db_backup.py в корне проекта (её же вызывает приложение
после первой записи тренировки за день). Восстановление описано там же.
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from db_backup import BACKUP_DIR_NAME, KEEP_DEFAULT, run_backup  # noqa: E402

DB_DEFAULT = os.path.join(REPO_ROOT, "training.db")
DEST_DEFAULT = os.path.join(REPO_ROOT, BACKUP_DIR_NAME)


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
