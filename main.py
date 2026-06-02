from flask import Flask, jsonify, request, abort, session, Response
from database import get_db, init_db
import os, shutil, csv, io, secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
import os

# ── Читаем секреты из файла config.py ───────────────────
try:
    import config as _cfg
    app.secret_key = _cfg.SECRET_KEY
    YANDEX_API_KEY = _cfg.YANDEX_API_KEY
    YANDEX_FOLDER_ID = _cfg.YANDEX_FOLDER_ID
    MAIL_SERVER   = getattr(_cfg, "MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT     = getattr(_cfg, "MAIL_PORT",     587)
    MAIL_USER     = getattr(_cfg, "MAIL_USER",     "")
    MAIL_PASSWORD = getattr(_cfg, "MAIL_PASSWORD", "")
    MAIL_FROM     = getattr(_cfg, "MAIL_FROM",     MAIL_USER)
    APP_URL       = getattr(_cfg, "APP_URL",       "https://nikitalisin.pythonanywhere.com")
except Exception:
    app.secret_key = "change-this-fallback"
    YANDEX_API_KEY = ""
    YANDEX_FOLDER_ID = ""
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USER = ""
    MAIL_PASSWORD = ""
    MAIL_FROM = ""
    APP_URL = "https://nikitalisin.pythonanywhere.com"

init_db()


def migrate_existing_data():
    """Привязывает существующие данные (user_id IS NULL) к первому пользователю."""
    conn = get_db()
    cur = conn.cursor()
    first_user = cur.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if first_user:
        uid = first_user["id"]
        cur.execute("UPDATE workout_log SET user_id = ? WHERE user_id IS NULL", (uid,))
        try:
            cur.execute("UPDATE recovery_log SET user_id = ? WHERE user_id IS NULL", (uid,))
        except Exception:
            pass
        conn.commit()
    conn.close()


def send_email(to, subject, body_html):
    """Отправка письма через SMTP. Молча проглатывает ошибки."""
    if not MAIL_USER or not MAIL_PASSWORD:
        return
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = MAIL_FROM
        msg["To"] = to
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as srv:
            srv.starttls()
            srv.login(MAIL_USER, MAIL_PASSWORD)
            srv.sendmail(MAIL_FROM, to, msg.as_string())
    except Exception:
        pass



# ══════════════════════════════════════════════
#  АВТОРИЗАЦИЯ
# ══════════════════════════════════════════════

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not email or "@" not in email:
        return jsonify({"status": "error", "message": "Неверный email"}), 400
    if len(password) < 6:
        return jsonify({"status": "error", "message": "Пароль минимум 6 символов"}), 400

    conn = get_db()
    cur = conn.cursor()
    existing = cur.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"status": "error", "message": "Email уже зарегистрирован"}), 409

    token = secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO users (email, password_hash, name, is_verified, verify_token) VALUES (?, ?, ?, 0, ?)",
        (email, generate_password_hash(password), name, token)
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    verify_url = f"{APP_URL}/verify-email?token={token}"
    send_email(email, "Подтверди email — Тренировочный дневник", f"""
        <p>Привет{', ' + name if name else ''}!</p>
        <p>Подтверди свой email, нажав на ссылку:</p>
        <p><a href="{verify_url}">{verify_url}</a></p>
    """)

    return jsonify({"status": "ok", "message": "Регистрация успешна. Проверь почту для подтверждения."})


@app.route("/verify-email")
def verify_email():
    token = request.args.get("token", "")
    if not token:
        return "Неверная ссылка", 400
    conn = get_db()
    cur = conn.cursor()
    user = cur.execute("SELECT id FROM users WHERE verify_token = ?", (token,)).fetchone()
    if not user:
        conn.close()
        return "Токен не найден или уже использован", 400
    cur.execute("UPDATE users SET is_verified = 1, verify_token = NULL WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return """<html><body style="font-family:sans-serif;text-align:center;padding:60px">
        <h2>✅ Email подтверждён!</h2>
        <p><a href="/">Войти в приложение</a></p>
    </body></html>"""


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = get_db()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, password_hash, name, is_verified FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"status": "error", "message": "Неверный email или пароль"}), 401
    if not user["is_verified"]:
        return jsonify({"status": "error", "message": "Подтверди email перед входом"}), 403

    session["auth"] = True
    session["user_id"] = user["id"]
    session["user_name"] = user["name"] or email
    return jsonify({"status": "ok", "name": user["name"] or email})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/check-auth")
def check_auth():
    if session.get("auth"):
        conn = get_db()
        user = conn.execute("SELECT is_admin FROM users WHERE id=?", (current_user_id(),)).fetchone()
        conn.close()
        is_admin = bool(user and user["is_admin"])
        return jsonify({"auth": True, "name": session.get("user_name", ""), "is_admin": is_admin})
    return jsonify({"auth": False})


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    conn = get_db()
    cur = conn.cursor()
    user = cur.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if user:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
            (token, expires, user["id"])
        )
        conn.commit()
        reset_url = f"{APP_URL}/reset-password?token={token}"
        send_email(email, "Сброс пароля — Тренировочный дневник", f"""
            <p>Ссылка для сброса пароля (действует 2 часа):</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
        """)
    conn.close()
    # Всегда отвечаем одинаково (безопасность)
    return jsonify({"status": "ok", "message": "Если email зарегистрирован — письмо отправлено"})


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        token = request.args.get("token", "")
        return f"""<html><body style="font-family:sans-serif;max-width:400px;margin:60px auto;padding:20px">
            <h2>Новый пароль</h2>
            <input id="pwd" type="password" placeholder="Новый пароль (мин. 6 символов)"
                   style="width:100%;padding:10px;margin:10px 0;box-sizing:border-box">
            <button onclick="resetPwd()" style="width:100%;padding:10px;background:#e31e24;color:white;border:none;cursor:pointer">
                Сохранить
            </button>
            <p id="msg"></p>
            <script>
            async function resetPwd() {{
                const res = await fetch('/reset-password', {{
                    method:'POST', headers:{{'Content-Type':'application/json'}},
                    body: JSON.stringify({{token:'{token}', password: document.getElementById('pwd').value}})
                }});
                const d = await res.json();
                document.getElementById('msg').textContent = d.message;
                if (d.status === 'ok') setTimeout(() => window.location='/', 2000);
            }}
            </script>
        </body></html>"""

    data = request.get_json() or {}
    token = data.get("token", "")
    new_pwd = data.get("password", "")
    if len(new_pwd) < 6:
        return jsonify({"status": "error", "message": "Пароль минимум 6 символов"}), 400
    conn = get_db()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, reset_token_expires FROM users WHERE reset_token = ?", (token,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "error", "message": "Токен не найден"}), 400
    if datetime.strptime(user["reset_token_expires"], "%Y-%m-%d %H:%M:%S") < datetime.now():
        conn.close()
        return jsonify({"status": "error", "message": "Ссылка устарела, запроси новую"}), 400
    cur.execute(
        "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
        (generate_password_hash(new_pwd), user["id"])
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": "Пароль обновлён! Перенаправляем..."})


def require_auth():
    if not session.get("auth"):
        abort(401, description="Не авторизован")


def current_user_id():
    return session.get("user_id")


# ══════════════════════════════════════════════
#  БЭКАП
# ══════════════════════════════════════════════
def backup_db():
    db_path = "training.db"
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    backup_path = os.path.join(backup_dir, f"training_{date_str}.db")
    if not os.path.exists(backup_path):
        shutil.copy2(db_path, backup_path)
    backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".db")])
    for old in backups[:-7]:
        os.remove(old)



# ══════════════════════════════════════════════
#  АДМИН
# ══════════════════════════════════════════════
def require_admin():
    if not session.get("auth"):
        abort(401)
    conn = get_db()
    user = conn.execute("SELECT is_admin FROM users WHERE id=?", (current_user_id(),)).fetchone()
    conn.close()
    if not user or not user["is_admin"]:
        abort(403)

@app.route("/admin/users")
def admin_users():
    require_admin()
    conn = get_db()
    users = conn.execute("""
        SELECT u.id, u.email, u.name, u.age, u.gender, u.is_verified, u.created_at,
               COUNT(DISTINCT wl.workout_date) as workout_count
        FROM users u
        LEFT JOIN workout_log wl ON wl.user_id = u.id AND wl.set_number > 0
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return jsonify({"users": [dict(u) for u in users]})


@app.route("/admin/toggle-admin/<int:user_id>", methods=["POST"])
def admin_toggle_admin(user_id):
    require_admin()
    if user_id == current_user_id():
        return jsonify({"status": "error", "message": "Нельзя изменить свои права"}), 400
    conn = get_db()
    user = conn.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "error", "message": "Пользователь не найден"}), 404
    new_val = 0 if user["is_admin"] else 1
    conn.execute("UPDATE users SET is_admin=? WHERE id=?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "is_admin": new_val})

@app.route("/admin/delete-user/<int:user_id>", methods=["DELETE"])
def admin_delete_user(user_id):
    require_admin()
    if user_id == current_user_id():
        return jsonify({"status": "error", "message": "Нельзя удалить себя"}), 400
    conn = get_db()
    conn.execute("DELETE FROM workout_log WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM recovery_log WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════
#  ПРОФИЛЬ
# ══════════════════════════════════════════════
@app.route("/profile", methods=["GET"])
def get_profile():
    require_auth()
    conn = get_db()
    user = conn.execute(
        "SELECT email, name, age, gender, weight_kg, height_cm, goal, created_at FROM users WHERE id = ?",
        (current_user_id(),)
    ).fetchone()
    conn.close()
    return jsonify(dict(user))

@app.route("/profile", methods=["POST"])
def update_profile():
    require_auth()
    data = request.get_json() or {}
    conn = get_db()
    conn.execute(
        "UPDATE users SET name=?, age=?, gender=?, weight_kg=?, height_cm=?, goal=? WHERE id=?",
        (data.get("name"), data.get("age"), data.get("gender"), data.get("weight_kg"), data.get("height_cm"), data.get("goal"), current_user_id())
    )
    conn.commit()
    conn.close()
    session["user_name"] = data.get("name") or session.get("user_name")
    return jsonify({"status": "ok"})

@app.route("/change-password", methods=["POST"])
def change_password():
    require_auth()
    data = request.get_json() or {}
    old_pwd = data.get("old_password", "")
    new_pwd = data.get("new_password", "")
    if len(new_pwd) < 6:
        return jsonify({"status": "error", "message": "Пароль минимум 6 символов"}), 400
    conn = get_db()
    user = conn.execute("SELECT password_hash FROM users WHERE id=?", (current_user_id(),)).fetchone()
    if not check_password_hash(user["password_hash"], old_pwd):
        conn.close()
        return jsonify({"status": "error", "message": "Неверный текущий пароль"}), 401
    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                 (generate_password_hash(new_pwd), current_user_id()))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": "Пароль изменён"})


@app.route("/body-weight", methods=["GET"])
def get_body_weight():
    require_auth()
    conn = get_db()
    rows = conn.execute("""
        SELECT log_date, weight_kg, notes FROM body_weight
        WHERE user_id = ? ORDER BY log_date DESC LIMIT 30
    """, (current_user_id(),)).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})

@app.route("/body-weight", methods=["POST"])
def save_body_weight():
    require_auth()
    data = request.get_json() or {}
    weight = data.get("weight_kg")
    if not weight or float(weight) <= 0:
        return jsonify({"status": "error", "message": "Неверный вес"}), 400
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    conn = get_db()
    conn.execute("""
        INSERT INTO body_weight (user_id, log_date, weight_kg, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, log_date) DO UPDATE SET
            weight_kg = excluded.weight_kg,
            notes = excluded.notes
    """, (current_user_id(), date, float(weight), data.get("notes")))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════
#  ДНИ И УПРАЖНЕНИЯ
# ══════════════════════════════════════════════
@app.route("/day/<int:day_id>")
def get_day(day_id):
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    day = cur.execute("SELECT id, name FROM day_templates WHERE id = ?", (day_id,)).fetchone()
    if not day:
        conn.close()
        abort(404, description="День не найден")
    exercises = cur.execute("""
        SELECT id, name, machine_model, plan_sets, plan_reps_range, default_weight, rest_seconds
        FROM exercises WHERE day_id = ? ORDER BY sort_order
    """, (day_id,)).fetchall()
    conn.close()
    return jsonify({"day": dict(day), "exercises": [dict(ex) for ex in exercises]})


# ══════════════════════════════════════════════
#  СОХРАНЕНИЕ ТРЕНИРОВКИ
# ══════════════════════════════════════════════
@app.route("/log", methods=["POST"])
def log_workout():
    require_auth()
    data = request.get_json()
    if not data:
        abort(400, description="Отсутствуют данные")
    conn = get_db()
    cur = conn.cursor()
    day = cur.execute("SELECT id FROM day_templates WHERE id = ?", (data["day_id"],)).fetchone()
    if not day:
        conn.close()
        abort(400, description="Неверный day_id")

    for ex_log in data["exercises"]:
        exercise = cur.execute(
            "SELECT id, default_weight FROM exercises WHERE id = ? AND day_id = ?",
            (ex_log["exercise_id"], data["day_id"])
        ).fetchone()
        if not exercise:
            conn.close()
            abort(400, description=f"Упражнение {ex_log['exercise_id']} не относится к дню {data['day_id']}")

        uid = current_user_id()
        # Защита от дублей
        cur.execute("DELETE FROM workout_log WHERE exercise_id = ? AND workout_date = ? AND (user_id = ? OR user_id IS NULL)",
                    (ex_log["exercise_id"], data["date"], uid))

        # Пропуск упражнения
        if ex_log.get("skipped"):
            cur.execute("""
                INSERT INTO workout_log (user_id, exercise_id, workout_date, set_number, weight, reps, difficulty, notes)
                VALUES (?, ?, ?, 0, 0, 0, 'пропущено', ?)
            """, (uid, ex_log["exercise_id"], data["date"], ex_log.get("skip_reason", "")))
            continue

        for s in ex_log["sets"]:
            weight = s.get("weight") if s.get("weight") is not None else exercise["default_weight"]
            cur.execute("""
                INSERT INTO workout_log (user_id, exercise_id, workout_date, set_number, weight, reps, difficulty, notes, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, ex_log["exercise_id"], data["date"], s["set_number"],
                  weight, s["reps"], s.get("difficulty"), s.get("notes"), data.get("duration_seconds")))

    conn.commit()
    conn.close()
    try:
        backup_db()
    except Exception:
        pass
    return jsonify({"status": "ok", "date": data["date"], "day_id": data["day_id"]})


# ══════════════════════════════════════════════
#  ПРОГРЕСС
# ══════════════════════════════════════════════
@app.route("/progress-by-name")
def get_progress_by_name():
    require_auth()
    name = request.args.get("name", "").strip()
    if not name:
        abort(400, description="Параметр name обязателен")
    limit = request.args.get("limit", 10, type=int)
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT wl.workout_date, wl.set_number, wl.weight, wl.reps, wl.difficulty
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE e.name = ? AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC, wl.set_number ASC
        LIMIT ?
    """, (name, uid, limit * 10)).fetchall()
    conn.close()
    return jsonify({"exercise_name": name, "history": [dict(r) for r in rows]})


@app.route("/workout-stats")
def workout_stats():
    require_auth()
    name = request.args.get("name", "").strip()
    if not name:
        abort(400, description="Параметр name обязателен")
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT wl.workout_date,
               MAX(wl.weight) as max_weight,
               SUM(wl.weight * wl.reps) as tonnage
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE e.name = ? AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        GROUP BY wl.workout_date
        ORDER BY wl.workout_date ASC
    """, (name, uid)).fetchall()
    conn.close()
    return jsonify({"exercise_name": name, "stats": [dict(r) for r in rows]})


# ══════════════════════════════════════════════
#  СРАВНЕНИЕ ДВУХ ТРЕНИРОВОК
# ══════════════════════════════════════════════
@app.route("/compare")
def compare_workouts():
    require_auth()
    date1 = request.args.get("date1", "").strip()
    date2 = request.args.get("date2", "").strip()
    if not date1 or not date2:
        abort(400, description="Нужны date1 и date2")
    conn = get_db()
    cur = conn.cursor()

    def get_day_data(date):
        uid = current_user_id()
        rows = cur.execute("""
            SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND wl.set_number > 0
              AND (wl.user_id = ? OR wl.user_id IS NULL)
            ORDER BY e.sort_order, wl.set_number
        """, (date, uid)).fetchall()
        # Группируем по упражнению
        result = {}
        for r in rows:
            name = r["name"]
            if name not in result:
                result[name] = {"sets": [], "max_weight": 0, "tonnage": 0}
            result[name]["sets"].append({"set": r["set_number"], "weight": r["weight"], "reps": r["reps"]})
            result[name]["max_weight"] = max(result[name]["max_weight"], r["weight"])
            result[name]["tonnage"] = round(result[name]["tonnage"] + r["weight"] * r["reps"], 1)
        return result

    data1 = get_day_data(date1)
    data2 = get_day_data(date2)

    # Объединяем все упражнения
    all_names = sorted(set(list(data1.keys()) + list(data2.keys())))
    comparison = []
    for name in all_names:
        d1 = data1.get(name, {})
        d2 = data2.get(name, {})
        comparison.append({
            "exercise": name,
            "date1": {"max_weight": d1.get("max_weight", 0), "tonnage": d1.get("tonnage", 0), "sets": d1.get("sets", [])},
            "date2": {"max_weight": d2.get("max_weight", 0), "tonnage": d2.get("tonnage", 0), "sets": d2.get("sets", [])},
            "weight_diff": round(d2.get("max_weight", 0) - d1.get("max_weight", 0), 1),
            "tonnage_diff": round(d2.get("tonnage", 0) - d1.get("tonnage", 0), 1)
        })

    conn.close()
    return jsonify({"date1": date1, "date2": date2, "comparison": comparison})


@app.route("/workout-dates")
def workout_dates():
    """Даты тренировок сгруппированные по дням (День 1/2/3)."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT DISTINCT wl.workout_date, e.day_id
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC
        LIMIT 60
    """, (uid,)).fetchall()
    conn.close()
    # Группируем по day_id
    from collections import defaultdict
    grouped = defaultdict(list)
    seen = set()
    for r in rows:
        key = (r["workout_date"], r["day_id"])
        if key not in seen:
            seen.add(key)
            grouped[r["day_id"]].append(r["workout_date"])
    return jsonify({"by_day": {str(k): v for k, v in sorted(grouped.items())}})


# ══════════════════════════════════════════════
#  РЕДАКТИРОВАНИЕ
# ══════════════════════════════════════════════
@app.route("/edit-log", methods=["POST"])
def edit_log():
    require_auth()
    data = request.get_json()
    if not data:
        abort(400, description="Нет данных")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE workout_log SET weight = ?, reps = ?, difficulty = ?
        WHERE exercise_id IN (SELECT id FROM exercises WHERE name = ?)
          AND workout_date = ? AND set_number = ?
    """, (data["weight"], data["reps"], data.get("difficulty"),
          data["exercise_name"], data["workout_date"], data["set_number"]))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/exercise/<int:exercise_id>", methods=["PUT"])
def update_exercise(exercise_id):
    require_auth()
    data = request.get_json()
    if not data:
        abort(400, description="Нет данных для обновления")
    conn = get_db()
    cur = conn.cursor()
    ex = cur.execute("SELECT id FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if not ex:
        conn.close()
        abort(404, description="Упражнение не найдено")
    allowed = ["name", "machine_model", "plan_sets", "plan_reps_range", "default_weight", "rest_seconds", "sort_order"]
    updates, params = [], []
    for field in allowed:
        if field in data and data[field] is not None:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        conn.close()
        abort(400, description="Нет полей для обновления")
    params.append(exercise_id)
    cur.execute(f"UPDATE exercises SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "exercise_id": exercise_id})


# ══════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════
@app.route("/last-weight/<int:exercise_id>")
def last_weight(exercise_id):
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    row = cur.execute("""
        SELECT wl.weight FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE e.name = (SELECT name FROM exercises WHERE id = ?) AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC, wl.set_number DESC LIMIT 1
    """, (exercise_id, uid)).fetchone()
    if row:
        conn.close()
        return jsonify({"weight": row["weight"]})
    ex = cur.execute("SELECT default_weight FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    conn.close()
    return jsonify({"weight": ex["default_weight"] if ex else 0})


@app.route("/exercise-names")
def get_exercise_names():
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    rows = cur.execute("SELECT DISTINCT name FROM exercises ORDER BY name").fetchall()
    conn.close()
    return jsonify({"names": [r["name"] for r in rows]})


@app.route("/stats-summary")
def stats_summary():
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    total = cur.execute("SELECT COUNT(DISTINCT workout_date) FROM workout_log WHERE (user_id = ? OR user_id IS NULL)", (uid,)).fetchone()[0]
    this_month = cur.execute("""
        SELECT COUNT(DISTINCT workout_date) FROM workout_log
        WHERE strftime('%Y-%m', workout_date) = strftime('%Y-%m', 'now')
          AND (user_id = ? OR user_id IS NULL)
    """, (uid,)).fetchone()[0]
    month_tonnage = cur.execute("""
        SELECT COALESCE(SUM(weight * reps), 0) FROM workout_log
        WHERE strftime('%Y-%m', workout_date) = strftime('%Y-%m', 'now') AND set_number > 0
          AND (user_id = ? OR user_id IS NULL)
    """, (uid,)).fetchone()[0]
    weeks = cur.execute("""
        SELECT DISTINCT strftime('%Y-%W', workout_date) as week
        FROM workout_log WHERE (user_id = ? OR user_id IS NULL) ORDER BY week DESC LIMIT 52
    """, (uid,)).fetchall()
    streak_weeks = 0
    today = datetime.today()
    for i in range(len(weeks)):
        expected = (today - timedelta(weeks=i)).strftime('%Y-%W')
        if i < len(weeks) and weeks[i]['week'] == expected:
            streak_weeks += 1
        else:
            break
    weekly_rows = cur.execute("""
        SELECT strftime('%Y-%W', workout_date) as week, SUM(weight * reps) as tonnage
        FROM workout_log WHERE set_number > 0 AND (user_id = ? OR user_id IS NULL)
        GROUP BY week ORDER BY week DESC LIMIT 12
    """, (uid,)).fetchall()
    weekly = [{"week": r["week"], "tonnage": round(r["tonnage"], 1)} for r in reversed(weekly_rows)]
    conn.close()
    return jsonify({
        "total_workouts": total, "this_month": this_month,
        "streak_weeks": streak_weeks, "month_tonnage": round(month_tonnage, 1),
        "weekly": weekly
    })


@app.route("/export-csv")
def export_csv():
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT wl.workout_date, dt.name as day_name, e.name as exercise,
               e.machine_model, wl.set_number, wl.weight, wl.reps,
               wl.difficulty, wl.notes, wl.created_at
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        JOIN day_templates dt ON dt.id = e.day_id
        WHERE wl.set_number > 0 AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC, e.sort_order, wl.set_number
    """, (uid,)).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "День", "Упражнение", "Тренажёр",
                     "Подход", "Вес (кг)", "Повторения", "Сложность", "Заметка", "Создано"])
    for r in rows:
        writer.writerow(list(r))
    filename = f"training_{datetime.now().strftime('%Y-%m-%d')}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ══════════════════════════════════════════════
#  PUSH-УВЕДОМЛЕНИЯ (Web Push)
# ══════════════════════════════════════════════
@app.route("/check-reminder")
def check_reminder():
    """Проверяет сколько дней прошло с последней тренировки."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    last = cur.execute("""
        SELECT workout_date FROM workout_log
        WHERE (user_id = ? OR user_id IS NULL)
        ORDER BY workout_date DESC LIMIT 1
    """, (uid,)).fetchone()
    conn.close()
    if not last:
        return jsonify({"days_since": None, "should_remind": False})
    last_date = datetime.strptime(last["workout_date"], "%Y-%m-%d").date()
    days_since = (datetime.now().date() - last_date).days
    return jsonify({
        "days_since": days_since,
        "last_date": last["workout_date"],
        "should_remind": days_since >= 3
    })


@app.route("/last-workout-days")
def last_workout_days():
    """Возвращает дни недели последних тренировок для отображения в статистике."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT DISTINCT workout_date FROM workout_log
        WHERE (user_id = ? OR user_id IS NULL)
        ORDER BY workout_date DESC LIMIT 30
    """, (uid,)).fetchall()
    conn.close()
    return jsonify({"dates": [r["workout_date"] for r in rows]})


@app.route("/personal-records")
def personal_records():
    """Личные рекорды — максимальный вес по каждому упражнению за всё время."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT e.name, MAX(wl.weight) as max_weight, wl.workout_date
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.set_number > 0 AND wl.weight > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        GROUP BY e.name
        ORDER BY e.name
    """, (uid,)).fetchall()
    conn.close()
    return jsonify({"records": [dict(r) for r in rows]})


@app.route("/progress-by-name-grouped")
def get_progress_grouped():
    """История подходов сгруппированная по датам."""
    require_auth()
    name = request.args.get("name", "").strip()
    if not name:
        abort(400, description="Параметр name обязателен")
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT wl.workout_date, wl.set_number, wl.weight, wl.reps, wl.difficulty
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE e.name = ? AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC, wl.set_number ASC
        LIMIT 100
    """, (name, uid)).fetchall()
    conn.close()
    # Группируем по дате
    from collections import OrderedDict
    grouped = OrderedDict()
    for r in rows:
        d = r["workout_date"]
        if d not in grouped:
            grouped[d] = []
        grouped[d].append(dict(r))
    return jsonify({"exercise_name": name, "grouped": [{"date": d, "sets": s} for d, s in grouped.items()]})


@app.route("/progression-hints")
def progression_hints():
    """Подсказки по прогрессии — анализирует последние оценки сложности."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    # Берём последнюю оценку для каждого упражнения
    uid = current_user_id()
    rows = cur.execute("""
        SELECT e.name, e.id, wl.difficulty, wl.weight, wl.workout_date
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.set_number > 0
        AND wl.difficulty IS NOT NULL AND wl.difficulty != ''
        AND (wl.user_id = ? OR wl.user_id IS NULL)
        AND wl.id IN (
            SELECT MAX(id) FROM workout_log
            WHERE set_number > 0 AND difficulty IS NOT NULL AND difficulty != ''
              AND (user_id = ? OR user_id IS NULL)
            GROUP BY exercise_id
        )
        ORDER BY e.name
    """, (uid, uid)).fetchall()
    conn.close()

    hints = {}
    for r in rows:
        diff = (r["difficulty"] or "").lower().strip()
        weight = r["weight"]
        # Определяем рекомендацию по системе оценок
        if "легко" in diff:
            # Шаг повышения: ноги +5, остальное +2.5
            step = 5.0 if any(w in r["name"].lower() for w in ["нога", "жим ног", "разгибани", "сгибани", "приводящ", "отводящ"]) else 2.5
            hints[r["name"]] = {
                "action": "increase",
                "icon": "📈",
                "text": f"Повышай до {weight + step} кг",
                "current_weight": weight,
                "suggested_weight": weight + step
            }
        elif "сложно" in diff:
            hints[r["name"]] = {
                "action": "ready",
                "icon": "🔜",
                "text": f"Готов к {weight + (5.0 if any(w in r['name'].lower() for w in ['нога','жим ног','разгибани','сгибани','приводящ','отводящ']) else 2.5)} кг",
                "current_weight": weight,
                "suggested_weight": weight + (5.0 if any(w in r["name"].lower() for w in ["нога","жим ног","разгибани","сгибани","приводящ","отводящ"]) else 2.5)
            }
        elif "тяжело" in diff:
            hints[r["name"]] = {
                "action": "hold",
                "icon": "🔒",
                "text": "Держи вес, шлифуй технику",
                "current_weight": weight,
                "suggested_weight": weight
            }

    return jsonify({"hints": hints})

# ══════════════════════════════════════════════
#  AI-АНАЛИЗ (Yandex AI Studio — DeepSeek V3)
# ══════════════════════════════════════════════
import urllib.request, json as _json

@app.route("/ai-analyze", methods=["POST"])
def ai_analyze():
    require_auth()
    data = request.get_json() or {}
    # Показатели восстановления от пользователя
    sleep = data.get("sleep", None)
    energy = data.get("energy", None)
    stress = data.get("stress", None)

    conn = get_db()
    cur = conn.cursor()

    # Последняя тренировка
    uid = current_user_id()
    last_date_row = cur.execute("""
        SELECT MAX(workout_date) as last_date FROM workout_log
        WHERE set_number > 0 AND (user_id = ? OR user_id IS NULL)
    """, (uid,)).fetchone()
    last_date = last_date_row["last_date"] if last_date_row else None

    # Определяем day_id последней тренировки
    last_day_id = None
    if last_date:
        r = cur.execute("""
            SELECT e.day_id FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND wl.set_number > 0
            LIMIT 1
        """, (last_date,)).fetchone()
        if r:
            last_day_id = r["day_id"]

    # Данные последней тренировки
    last_sets = []
    if last_date:
        last_duration = cur.execute("SELECT MAX(duration_seconds) as dur FROM workout_log WHERE workout_date = ? AND (user_id = ? OR user_id IS NULL)", (last_date, uid)).fetchone()
        last_dur_min = round(last_duration["dur"] / 60) if last_duration and last_duration["dur"] else None
        last_sets = cur.execute("""
            SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND wl.set_number > 0
              AND (wl.user_id = ? OR wl.user_id IS NULL)
            ORDER BY e.sort_order, wl.set_number
        """, (last_date, uid)).fetchall()

    # Предыдущая тренировка того же дня
    prev_sets = []
    if last_date and last_day_id:
        prev_date_row = cur.execute("""
            SELECT MAX(wl.workout_date) as prev_date
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date < ? AND e.day_id = ? AND wl.set_number > 0
        """, (last_date, last_day_id)).fetchone()
        prev_date = prev_date_row["prev_date"] if prev_date_row else None
        if prev_date:
            prev_sets = cur.execute("""
                SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty
                FROM workout_log wl
                JOIN exercises e ON e.id = wl.exercise_id
                WHERE wl.workout_date = ? AND wl.set_number > 0
                  AND (wl.user_id = ? OR wl.user_id IS NULL)
                ORDER BY e.sort_order, wl.set_number
            """, (prev_date, uid)).fetchall()

    # Тоннаж по неделям за 30 дней
    weekly = cur.execute("""
        SELECT strftime('%Y-%W', workout_date) as week, SUM(weight * reps) as tonnage
        FROM workout_log WHERE set_number > 0
        AND workout_date >= date('now', '-30 days')
        AND (user_id = ? OR user_id IS NULL)
        GROUP BY week ORDER BY week
    """, (uid,)).fetchall()

    # Макс веса по упражнениям
    records = cur.execute("""
        SELECT e.name, MAX(wl.weight) as max_weight
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.set_number > 0 AND (wl.user_id = ? OR wl.user_id IS NULL)
        GROUP BY e.name
    """, (uid,)).fetchall()

    conn.close()

    # Форматируем данные
    def fmt_sets(sets):
        lines = []
        cur_ex = None
        for r in sets:
            if r["name"] != cur_ex:
                cur_ex = r["name"]
                lines.append(cur_ex + ":")
            lines.append("  П" + str(r["set_number"]) + ": " + str(r["weight"]) + "кг x" + str(r["reps"]) + " (" + (r["difficulty"] or "-") + ")")
        return "\n".join(lines)

    last_summary = fmt_sets(last_sets) if last_sets else "нет данных"
    prev_summary = fmt_sets(prev_sets) if prev_sets else "нет данных"
    weekly_summary = ", ".join(["нед." + r["week"][-2:] + ": " + str(round(r["tonnage"])) + "кг" for r in weekly])
    records_summary = ", ".join([r["name"] + " " + str(r["max_weight"]) + "кг" for r in records])

    recovery = ""
    if sleep or energy or stress:
        recovery = (
            "\n\nПОКАЗАТЕЛИ ВОССТАНОВЛЕНИЯ:\n"
            + ("Сон: " + str(sleep) + "/5\n" if sleep else "")
            + ("Энергия: " + str(energy) + "/5\n" if energy else "")
            + ("Стресс: " + str(stress) + "/5\n" if stress else "")
        )

    # Загружаем прошлые рекомендации
    conn2 = get_db()
    past_recs = conn2.execute("""
        SELECT workout_date, recommendation_text FROM ai_recommendations
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 2
    """, (uid,)).fetchall()

    # Формируем блок памяти для промпта
    memory_block = ""
    if past_recs:
        memory_block = "\nПРОШЛЫЕ РЕКОМЕНДАЦИИ AI:\n"
        for rec in reversed(past_recs):
            # Берём только таблицу весов из прошлого ответа (первые 800 символов)
            rec_short = rec["recommendation_text"][:800]
            memory_block += f"Дата тренировки {rec['workout_date']}:\n{rec_short}\n---\n"
        memory_block += "Учти: выполнил ли пользователь прошлые рекомендации по весам — сравни с ПОСЛЕДНЕЙ ТРЕНИРОВКОЙ.\n"
    conn2.close()

    # Получаем профиль для AI
    conn2 = get_db()
    profile = conn2.execute("SELECT age, gender, weight_kg, height_cm, goal FROM users WHERE id=?", (uid,)).fetchone()
    conn2.close()
    profile_str = ""
    if profile:
        if profile["age"]: profile_str += f"Возраст: {profile['age']} лет. "
        if profile["gender"]: profile_str += f"Пол: {profile['gender']}. "
        if profile["weight_kg"]: profile_str += f"Вес тела: {profile['weight_kg']} кг. "
        if profile["height_cm"]: profile_str += f"Рост: {profile['height_cm']} см. "
        if profile["goal"]: profile_str += f"Цель: {profile['goal']}. "

    # Динамика веса тела
    conn3 = get_db()
    bw_rows = conn3.execute("""
        SELECT log_date, weight_kg FROM body_weight
        WHERE user_id = ? ORDER BY log_date DESC LIMIT 5
    """, (uid,)).fetchall()
    conn3.close()
    if bw_rows:
        bw_str = ", ".join([f"{r['log_date']}: {r['weight_kg']} кг" for r in reversed(bw_rows)])
        profile_str += f"Динамика веса: {bw_str}. "

    prompt = (
        "Ты — персональный AI-тренер и спортивный врач. Тренируюсь 3 раза в неделю "
        "(день 1: верх, день 2: ноги+талия, день 3: верх). Цели: рост силы, контроль техники, профилактика травм.\n"
        + ("ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ: " + profile_str + "\n" if profile_str else "")
        + "\n"
        + memory_block
        + "ПОСЛЕДНЯЯ ТРЕНИРОВКА (" + (last_date or "?") + ((" [" + str(last_dur_min) + " мин]") if last_dur_min else "") + ":\n" + last_summary + "\n\n"
        "ПРЕДЫДУЩАЯ ТРЕНИРОВКА ЭТОГО ДНЯ:\n" + prev_summary + "\n\n"
        "ТОННАЖ ПО НЕДЕЛЯМ (30 дней): " + weekly_summary + "\n"
        "ЛИЧНЫЕ РЕКОРДЫ: " + records_summary +
        recovery + "\n\n"
        "ПРАВИЛА ОТВЕТА:\n"
        "1. ПЕРСОНАЛИЗАЦИЯ ОБЯЗАТЕЛЬНА: в блоке 'Оценка прошедшей тренировки' первым предложением ОБЯЗАТЕЛЬНО напиши все данные профиля и вывод. Пример: 'Для мужчины 32 лет, рост 170 см, вес 72 кг, цель — рост силы: тоннаж вырос на X кг.' В финальном вердикте обязательно учти цель пользователя — например при цели 'похудение' не рекомендуй увеличивать объём, при цели 'рост силы' — приоритет прогрессии весов. Если профиль не заполнен — пропусти.\n"
        "2. Формулируй уверенно. ЗАПРЕЩЕНЫ слова: 'возможно', 'может быть', 'вероятно', 'возможное'. Делай наиболее обоснованный вывод на основе данных. Если данных недостаточно — напиши: 'недостаточно данных для вывода'.\n"
        "3. СТРОГО ЗАПРЕЩЕНО использовать слова 'легко', 'тяжело', 'с запасом' — эти слова под запретом полностью. Только факты из данных: 'повторения стабильны', 'повторения снизились на X', 'тоннаж вырос на Y кг'. Нарушение этого правила недопустимо.\n"
        "4. Вердикт ДОЛЖЕН совпадать с таблицей весов: если 50%+ упражнений снижают/держат вес — вердикт 'восстановление', не прогрессия.\n"
        "5. Практический совет — персональный. Учитывай профиль, самочувствие, длительность тренировки. Не упоминай анаболическое окно.\n\n"
        "Ответ строго в формате:\n\n"
        "**📊 Оценка прошедшей тренировки**\n"
        "- Сравни с предыдущей: изменение тоннажа, новые рекорды.\n"
        "- 1-2 упражнения где падали повторения — укажи конкретную причину (не 'возможно').\n\n"
        "**🎯 Индекс готовности**\n"
        "Таблица: Показатель | Оценка | Причина\n"
        "Строки:\n"
        "- Выполнение подходов (X/10): укажи % выполненных повторений от плана\n"
        "- Восстановление (X/10): укажи конкретные признаки — падение повторений, динамика тоннажа\n"
        "- Стабильность нагрузки (X/10): сравни с предыдущей тренировкой этого дня\n"
        "- Общая готовность (X/10): среднее, округлённое\n"
        "Вывод одной строкой: готовность X/10 → разрешена/ограничена/запрещена прогрессия.\n\n"
        "**🩺 Восстановление**\n"
        "- Риск перетренированности: низкий/средний/высокий — с обоснованием.\n"
        "- Если средний или высокий — конкретное действие сегодня.\n\n"
        "**📈 Прогресс за 30 дней**\n"
        "- 2-3 упражнения с наибольшим приростом.\n"
        "- 1-2 упражнения где прогресс застопорился — причина.\n"
        "- Итог по тоннажу: растёт/стабилен/падает.\n\n"
        "**📋 Веса на следующую тренировку**\n"
        "Таблица: Упражнение | Текущий | Рекомендуемый | Причина\n"
        "Правила прогрессии:\n"
        "- Все подходы легко (оценка 'Легко') → +2.5кг\n"
        "- Последние подходы тяжело → держать вес\n"
        "- Падение повторений → -2.5кг\n"
        "- Если вердикт 'восстановление' → не повышать вес ни в одном упражнении\n""- Если цель 'рост силы' И готовность ≥ 6 → повышать вес в упражнениях где повторения стабильны, даже при умеренной готовности\n""- Если цель 'похудение' → не увеличивать общий объём, приоритет технике\n""- Если цель 'набор массы' → при стабильных повторениях всегда +2.5кг\n\n"
        "**⚖️ Финальный вердикт**\n"
        "- Вердикт ЛОГИЧЕСКИ следует из индекса готовности и таблицы весов. Не противоречит им.\n"
        "- Если индекс готовности < 6 → 'Снижаем интенсивность на X%', если 6-8 → 'Умеренная тренировка', если > 8 → 'Работаем в полную силу'.\n"
        "- Один персональный совет на СЕГОДНЯ: конкретное действие с учётом профиля и самочувствия. Не упоминай 'анаболическое окно' и '30г белка сразу после' — это устаревшие рекомендации.\n\n"
        "ВАЖНО: все веса кратны 2.5. Таблицы строго в markdown. Только цифры и конкретика. Без слова 'может'."
    )

    try:
        payload = _json.dumps({
            "modelUri": "gpt://" + YANDEX_FOLDER_ID + "/yandexgpt",
            "completionOptions": {
                "stream": False,
                "temperature": 0.5,
                "maxTokens": 2000
            },
            "messages": [{"role": "user", "text": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Api-Key " + YANDEX_API_KEY,
                "x-folder-id": YANDEX_FOLDER_ID
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read().decode("utf-8"))
            answer = result["result"]["alternatives"][0]["message"]["text"]
            # Сохраняем рекомендацию в историю
            try:
                conn3 = get_db()
                conn3.execute(
                    "INSERT INTO ai_recommendations (user_id, workout_date, recommendation_text) VALUES (?, ?, ?)",
                    (uid, last_date or datetime.now().strftime("%Y-%m-%d"), answer)
                )
                conn3.commit()
                conn3.close()
            except Exception:
                pass
            return jsonify({"status": "ok", "analysis": answer})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ══════════════════════════════════════════════
#  RECOVERY — сохранение показателей самочувствия
# ══════════════════════════════════════════════


@app.route("/recovery", methods=["POST"])
def save_recovery():
    require_auth()
    data = request.get_json() or {}
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    cur.execute("""
        INSERT INTO recovery_log (user_id, log_date, sleep, energy, stress, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, log_date) DO UPDATE SET
            sleep = excluded.sleep,
            energy = excluded.energy,
            stress = excluded.stress,
            notes = excluded.notes
    """, (uid, date, data.get("sleep"), data.get("energy"), data.get("stress"), data.get("notes")))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/recovery-history")
def recovery_history():
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    rows = cur.execute("""
        SELECT r.log_date, r.sleep, r.energy, r.stress,
               COUNT(DISTINCT wl.exercise_id) as exercises_count,
               COALESCE(SUM(wl.weight * wl.reps), 0) as tonnage
        FROM recovery_log r
        LEFT JOIN workout_log wl ON wl.workout_date = r.log_date AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        WHERE (r.user_id = ? OR r.user_id IS NULL)
        GROUP BY r.log_date
        ORDER BY r.log_date DESC
        LIMIT 30
    """, (uid, uid)).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})


# ══════════════════════════════════════════════
#  PR-СИСТЕМА — личные рекорды при сохранении
# ══════════════════════════════════════════════
@app.route("/check-pr", methods=["POST"])
def check_pr():
    """Проверяет установлены ли новые рекорды в последней тренировке."""
    require_auth()
    data = request.get_json() or {}
    date = data.get("date")
    if not date:
        abort(400)

    conn = get_db()
    cur = conn.cursor()

    # Рекорды из последней тренировки
    uid = current_user_id()
    new_records = cur.execute("""
        SELECT e.name,
               MAX(wl.weight) as max_weight,
               MAX(wl.reps) as max_reps,
               SUM(wl.weight * wl.reps) as tonnage
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.workout_date = ? AND wl.set_number > 0
          AND (wl.user_id = ? OR wl.user_id IS NULL)
        GROUP BY e.name
    """, (date, uid)).fetchall()

    prs = []
    for r in new_records:
        # Предыдущий рекорд веса для этого упражнения
        prev = cur.execute("""
            SELECT MAX(wl.weight) as prev_max_weight,
                   MAX(wl.reps) as prev_max_reps
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE e.name = ? AND wl.workout_date < ? AND wl.set_number > 0
              AND (wl.user_id = ? OR wl.user_id IS NULL)
        """, (r["name"], date, uid)).fetchone()

        if prev and prev["prev_max_weight"]:
            if r["max_weight"] > prev["prev_max_weight"]:
                prs.append({
                    "exercise": r["name"],
                    "type": "weight",
                    "old": prev["prev_max_weight"],
                    "new": r["max_weight"]
                })
            elif r["max_reps"] > (prev["prev_max_reps"] or 0) and r["max_weight"] >= prev["prev_max_weight"]:
                prs.append({
                    "exercise": r["name"],
                    "type": "reps",
                    "old": prev["prev_max_reps"],
                    "new": r["max_reps"]
                })

    conn.close()
    return jsonify({"prs": prs})



@app.route("/ai-history")
def ai_history():
    require_auth()
    conn = get_db()
    rows = conn.execute("""
        SELECT id, workout_date, recommendation_text, created_at
        FROM ai_recommendations
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (current_user_id(),)).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})

# ══════════════════════════════════════════════
#  ДЕМО-РЕЖИМ
# ══════════════════════════════════════════════
@app.route("/restore-backup", methods=["POST"])
def restore_backup():
    """Восстанавливает workout_log пользователя из бэкапа до демо."""
    require_auth()
    uid = current_user_id()
    pre_demo = os.path.join("backups", "training_pre_demo.db")
    if not os.path.exists(pre_demo):
        return jsonify({"status": "error", "message": "Бэкап до демо не найден"}), 404
    try:
        import sqlite3 as _sqlite3
        backup_conn = _sqlite3.connect(pre_demo)
        backup_conn.row_factory = _sqlite3.Row
        rows = backup_conn.execute(
            "SELECT * FROM workout_log WHERE user_id = ? OR user_id IS NULL", (uid,)
        ).fetchall()
        backup_conn.close()
        conn = get_db()
        conn.execute("DELETE FROM workout_log WHERE user_id = ?", (uid,))
        for r in rows:
            conn.execute("""
                INSERT INTO workout_log
                (user_id, exercise_id, workout_date, set_number, weight, reps, difficulty, notes, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, r["exercise_id"], r["workout_date"], r["set_number"],
                  r["weight"], r["reps"], r["difficulty"], r["notes"],
                  r["duration_seconds"] if "duration_seconds" in r.keys() else None))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": "Данные восстановлены"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/load-demo", methods=["POST"])
def load_demo():
    """Загружает красивые демо-данные для питча."""
    require_auth()
    # Сохраняем бэкап ПЕРЕД загрузкой демо
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    pre_demo = os.path.join(backup_dir, "training_pre_demo.db")
    if os.path.exists("training.db"):
        shutil.copy2("training.db", pre_demo)
    conn = get_db()
    cur = conn.cursor()

    # Очищаем лог только для текущего пользователя
    uid = current_user_id()
    cur.execute("DELETE FROM workout_log WHERE user_id = ?", (uid,))

    # Генерируем 8 недель красивых данных с прогрессом
    from datetime import date, timedelta
    import random

    # Дни тренировок — понедельник, среда, пятница
    start = date.today() - timedelta(weeks=8)
    workout_days = []
    d = start
    while d <= date.today():
        if d.weekday() in [0, 2, 4]:  # пн, ср, пт
            workout_days.append(d)
        d += timedelta(days=1)

    # Упражнения с прогрессирующими весами
    day1_exercises = [
        (1, [32.5, 35, 37.5, 40]),      # Тяга верхнего блока
        (2, [30, 32.5, 35, 37.5]),      # Жим плечами
        (3, [32.5, 35, 37.5, 40]),      # Жим грудью
        (5, [15, 17.5, 17.5, 20]),      # Обратная бабочка
        (6, [17.5, 20, 20, 20]),        # Бицепс
        (7, [0, 5, 5, 5]),              # Пресс
    ]
    day2_exercises = [
        (8, [30, 32.5, 35, 37.5]),      # Разгибание ног
        (9, [25, 27.5, 30, 32.5]),      # Сгибание ног
        ("Горизонтальный жим ногами", [60, 65, 70, 75]),  # Жим ногами
        (10, [30, 32.5, 35, 35]),       # Приводящая
        (11, [35, 37.5, 40, 40]),       # Отводящая
    ]
    day3_exercises = [
        (14, [30, 32.5, 35, 37.5]),     # Жим плечами
        (15, [35, 37.5, 40, 40]),       # Тяга узкий хват
        (16, [35, 37.5, 40, 40]),       # Жим грудью
        (17, [30, 32.5, 35, 35]),       # Тяга к поясу
        (18, [10, 12.5, 15, 15]),       # Трицепс
        (19, [0, 5, 5, 5]),             # Пресс
    ]

    difficulties = ['Легко', 'Легко', 'Сложно', 'Тяжело', 'Сложно']
    day_cycle = [day1_exercises, day2_exercises, day3_exercises]
    day_ids = [1, 2, 3]

    for i, workout_date in enumerate(workout_days):
        day_idx = i % 3
        exercises = day_cycle[day_idx]
        week_num = i // 3
        # Прогресс — каждые 2 недели +2.5 кг
        progress = (week_num // 2) * 2.5

        for ex_id, base_weights in exercises:
            if isinstance(ex_id, str):
                ex = cur.execute("SELECT id, plan_sets FROM exercises WHERE name=?", (ex_id,)).fetchone()
                if ex: ex_id = ex["id"]
            else:
                ex = cur.execute("SELECT id, plan_sets FROM exercises WHERE id=?", (ex_id,)).fetchone()
            if not ex:
                continue
            plan_sets = ex["plan_sets"]
            diff = difficulties[week_num % len(difficulties)]

            for set_num in range(1, plan_sets + 1):
                w_idx = min(set_num - 1, len(base_weights) - 1)
                weight = max(0, base_weights[w_idx] + progress)
                # Последний подход чуть меньше повторений иногда
                if set_num == plan_sets and week_num < 3:
                    reps = random.choice([10, 11, 12])
                else:
                    reps = random.choice([11, 12, 12, 13])

                cur.execute("""
                    INSERT INTO workout_log
                    (user_id, exercise_id, workout_date, set_number, weight, reps, difficulty)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (uid, ex_id, workout_date.isoformat(), set_num, weight, reps, diff))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "workouts": len(workout_days)})


@app.route("/workout-history")
def workout_history():
    """Список всех тренировок с деталями."""
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    # Получаем все уникальные даты с day_id
    uid = current_user_id()
    dates = cur.execute("""
        SELECT DISTINCT wl.workout_date, e.day_id, dt.name as day_name
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        JOIN day_templates dt ON dt.id = e.day_id
        WHERE wl.set_number > 0 AND (wl.user_id = ? OR wl.user_id IS NULL)
        ORDER BY wl.workout_date DESC
        LIMIT 50
    """, (uid,)).fetchall()

    result = []
    for d in dates:
        # Получаем упражнения за этот день
        sets = cur.execute("""
            SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty,
                   0 as ex_tonnage,
                   (SELECT MAX(duration_seconds) FROM workout_log
                    WHERE workout_date = ? AND (user_id = ? OR user_id IS NULL)) as duration_seconds
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND e.day_id = ? AND wl.set_number > 0
              AND (wl.user_id = ? OR wl.user_id IS NULL)
            ORDER BY e.sort_order, wl.set_number
        """, (d["workout_date"], uid, d["workout_date"], d["day_id"], uid)).fetchall()

        total_tonnage = sum(r["weight"] * r["reps"] for r in sets)

        # Группируем по упражнению
        exercises = {}
        for s in sets:
            if s["name"] not in exercises:
                exercises[s["name"]] = []
            exercises[s["name"]].append({
                "set": s["set_number"],
                "weight": s["weight"],
                "reps": s["reps"],
                "difficulty": s["difficulty"]
            })

        result.append({
            "date": d["workout_date"],
            "day_name": d["day_name"],
            "total_tonnage": round(total_tonnage),
            "exercises": exercises
        })

    conn.close()
    return jsonify({"history": result})