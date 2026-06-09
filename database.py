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

    # exercises: user_id — кому принадлежат упражнения.
    # NULL = системный шаблон (используется как эталон для копирования).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id INTEGER NOT NULL,
            user_id INTEGER,
            name TEXT NOT NULL,
            machine_model TEXT,
            plan_sets INTEGER,
            plan_reps_range TEXT,
            default_weight REAL,
            rest_seconds INTEGER,
            sort_order INTEGER,
            FOREIGN KEY (day_id) REFERENCES day_templates(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
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
            log_date TEXT NOT NULL,
            sleep INTEGER,
            energy INTEGER,
            stress INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workout_date TEXT NOT NULL,
            recommendation_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_rec_user ON ai_recommendations(user_id, workout_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workout_user_date ON workout_log(user_id, workout_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workout_exercise ON workout_log(exercise_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recovery_user ON recovery_log(user_id)")

    # Фикс #1: удаляем старый уникальный индекс на одном log_date (без user_id),
    # который вызывает IntegrityError при нескольких пользователях с одной датой.
    try:
        indexes = cur.execute("PRAGMA index_list('recovery_log')").fetchall()
        for idx in indexes:
            idx_name = idx[1]
            idx_unique = idx[2]
            idx_info = cur.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
            cols = [i[2] for i in idx_info]
            if idx_unique and cols == ["log_date"]:
                cur.execute(f"DROP INDEX IF EXISTS \"{idx_name}\"")
    except Exception:
        pass

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_recovery_user_date ON recovery_log(user_id, log_date)")

    # ── Миграции ────────────────────────────────────────────────

    # workout_log: duration_seconds
    try:
        cur.execute("ALTER TABLE workout_log ADD COLUMN duration_seconds INTEGER")
    except Exception:
        pass

    # exercises: user_id — ключевая миграция для мульти-пользователей
    try:
        cur.execute("ALTER TABLE exercises ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except Exception:
        pass

    cur.execute("CREATE INDEX IF NOT EXISTS idx_exercises_user ON exercises(user_id, day_id)")

    # Таблица веса тела
    cur.execute("""
        CREATE TABLE IF NOT EXISTS body_weight (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_body_weight_user_date ON body_weight(user_id, log_date)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS body_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            chest_cm REAL,
            waist_cm REAL,
            hips_cm REAL,
            shoulder_cm REAL,
            bicep_cm REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_user_date ON body_measurements(user_id, log_date)")

    for col, typ in [("age", "INTEGER"), ("gender", "TEXT"), ("weight_kg", "REAL"), ("goal", "TEXT"), ("height_cm", "INTEGER"), ("is_admin", "INTEGER DEFAULT 0")]:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except Exception:
            pass

    try:
        cur.execute("ALTER TABLE workout_log ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except Exception:
        pass

    try:
        cur.execute("ALTER TABLE recovery_log ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS progress_summary_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            summary_text TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_workout_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            summary_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_hist_user ON ai_analysis_history(user_id, created_at)")

        conn.commit()
    conn.close()


def seed():
    """Засевает системные шаблоны дней и упражнений (user_id=NULL = системный эталон)."""
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
        (3, "Разгибание на трицепс",             "№14", 2, "10–12", 10.0,  60, 5),
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


def seed_user(user_id):
    """
    Копирует системные упражнения (user_id IS NULL) новому пользователю.
    Идемпотентна: если у пользователя уже есть свои упражнения — ничего не делает.

    Архитектура:
        exercises WHERE user_id IS NULL  — системные шаблоны (эталон)
        exercises WHERE user_id = <id>   — личная копия пользователя

    При переходе на Вариант 2 (библиотека + программы) эта функция
    заменяется на создание записей в WorkoutTemplate + ProgramExercise.
    """
    conn = get_db()
    cur = conn.cursor()

    # Идемпотентность: уже засеяно — выходим
    existing = cur.execute(
        "SELECT id FROM exercises WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone()
    if existing:
        conn.close()
        return

    # Копируем системные упражнения для каждого дня
    system_exercises = cur.execute(
        "SELECT day_id, name, machine_model, plan_sets, plan_reps_range, "
        "default_weight, rest_seconds, sort_order "
        "FROM exercises WHERE user_id IS NULL ORDER BY day_id, sort_order"
    ).fetchall()

    for ex in system_exercises:
        cur.execute(
            "INSERT INTO exercises "
            "(user_id, day_id, name, machine_model, plan_sets, plan_reps_range, "
            "default_weight, rest_seconds, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, ex["day_id"], ex["name"], ex["machine_model"],
             ex["plan_sets"], ex["plan_reps_range"], ex["default_weight"],
             ex["rest_seconds"], ex["sort_order"])
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    seed()
    print("База данных готова.")