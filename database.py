import sqlite3

DB_NAME = "training.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # ── Пользователи ──────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name TEXT,
            is_verified INTEGER DEFAULT 0,
            verify_token TEXT,
            reset_token TEXT,
            reset_token_expires TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS day_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            machine_model TEXT,
            plan_sets INTEGER,
            plan_reps_range TEXT,
            default_weight REAL,
            rest_seconds INTEGER,
            sort_order INTEGER,
            FOREIGN KEY (day_id) REFERENCES day_templates(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workout_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exercise_id INTEGER NOT NULL,
            workout_date TEXT NOT NULL,
            set_number INTEGER,
            weight REAL,
            reps INTEGER,
            difficulty TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (exercise_id) REFERENCES exercises(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recovery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            log_date TEXT NOT NULL UNIQUE,
            sleep INTEGER,
            energy INTEGER,
            stress INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Индексы для производительности
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workout_user_date ON workout_log(user_id, workout_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workout_exercise ON workout_log(exercise_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recovery_user ON recovery_log(user_id)")

    # Добавляем user_id в workout_log если его ещё нет (миграция)
    try:
        cur.execute("ALTER TABLE workout_log ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except Exception:
        pass  # Колонка уже есть

    # Добавляем user_id в recovery_log если есть (миграция)
    try:
        cur.execute("ALTER TABLE recovery_log ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except Exception:
        pass

    conn.commit()
    conn.close()

def seed():
    conn = get_db()
    cur = conn.cursor()

    days = [
        (1, "День 1 – ВЕРХ (ширина спины, плечи, грудь)", 1),
        (2, "День 2 – НОГИ + ТАЛИЯ", 2),
        (3, "День 3 – ВЕРХ (плечи, спина, руки)", 3)
    ]
    for day_id, name, sort in days:
        cur.execute(
            "INSERT OR IGNORE INTO day_templates (id, name, sort_order) VALUES (?, ?, ?)",
            (day_id, name, sort)
        )

    exercises = [
        # День 1
        (1, "Тяга верхнего блока",             "№30", 4, "8–12",  40.0,  90, 1),
        (1, "Жим плечами (дельтоидный)",        "№22", 4, "8–12",  35.0,  90, 2),
        (1, "Вертикальный жим грудью",           "№28", 3, "8–12",  40.0,  90, 3),
        (1, "Сведение рук в Peck Deck (грудь)",  "№23", 3, "12–15", 20.0,  60, 4),
        (1, "Обратная бабочка (задние дельты)",  "№23", 3, "12–15", 15.0,  60, 5),
        (1, "Сгибание рук (бицепс)",             "№31", 2, "10–12", 20.0,  60, 6),
        (1, "Пресс",                             "—",   3, "12–15",  5.0,  60, 7),
        # День 2
        (2, "Разгибание ног",                    "№24", 3, "12–15", 35.0,  60, 1),
        (2, "Сгибание ног",                      "№19", 3, "12–15", 30.0,  60, 2),
        (2, "Горизонтальный жим ногами",         "№18", 3, "10–12", 70.0,  90, 3),
        (2, "Приводящая машина",                 "№27", 3, "12–15", 35.0,  60, 4),
        (2, "Отводящая машина",                  "№25", 3, "15",    40.0,  60, 5),
        (2, "Гиперэкстензия (поясница)",         "—",   2, "15–20",  0.0,  45, 6),
        (2, "Косые мышцы",                       "—",   2, "15–20",  0.0,  45, 7),
        # День 3
        (3, "Жим плечами (дельтоидный)",         "№22", 4, "10–12", 35.0,  90, 1),
        (3, "Тяга верхнего блока (узкий хват)",  "№30", 3, "10–12", 40.0,  90, 2),
        (3, "Вертикальный жим грудью",           "№28", 3, "10–12", 40.0,  90, 3),
        (3, "Тяга блока к поясу",                "№26", 3, "10–12", 35.0,  90, 4),
        (3, "Разгибание на трицепс", "№14", 2, "10–12", 10.0,  60, 5),
        (3, "Пресс",                             "—",   3, "12–15",  5.0,  60, 6),
    ]
    for ex in exercises:
        cur.execute(
            "INSERT OR IGNORE INTO exercises "
            "(day_id, name, machine_model, plan_sets, plan_reps_range, default_weight, rest_seconds, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ex
        )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed()
    print("База данных готова.")
