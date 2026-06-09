from flask import Flask, jsonify, request, abort, session, Response
from database import get_db, init_db, seed_user
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

# Засев программы для существующих пользователей без своих упражнений
def _seed_existing_users():
    conn = get_db()
    users = conn.execute("""
        SELECT u.id FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM exercises e WHERE e.user_id = u.id)
    """).fetchall()
    conn.close()
    for u in users:
        seed_user(u["id"])
_seed_existing_users()

import logging, os
from logging.handlers import RotatingFileHandler

os.makedirs('/home/NikitaLisin/logs', exist_ok=True)
log_handler = RotatingFileHandler(
    '/home/NikitaLisin/logs/app.log',
    maxBytes=1024*1024,
    backupCount=5,
    encoding='utf-8'
)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger = logging.getLogger('progressor')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

def send_telegram(message):
    """Отправляет уведомление об ошибке на email (Telegram недоступен на free PythonAnywhere)."""
    try:
        import config as _cfg
        to = getattr(_cfg, 'MAIL_USER', '')
        if not to:
            return
        clean = message.replace('<b>', '').replace('</b>', '').replace('<br>', ' ')
        send_email(to, 'Progressor Error', f'<pre>{clean}</pre>')
    except Exception:
        pass


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
    """Отправка письма через SMTP."""
    if not MAIL_USER or not MAIL_PASSWORD:
        logger.warning(f"MAIL_NOT_CONFIGURED — письмо не отправлено ({to})")
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
        logger.info(f"EMAIL_SENT to={to} subject={subject}")
    except Exception as e:
        logger.error(f"EMAIL_ERROR to={to} subject={subject} error={str(e)}")



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

    # Копируем системную программу новому пользователю
    seed_user(user_id)

    verify_url = f"{APP_URL}/verify-email?token={token}"
    send_email(email, "Подтверди email — Progressor", f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;background:#0f1117;border-radius:16px;overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1a3d28,#2ecc71);padding:32px;text-align:center;">
            <img src="https://nikitalisin.pythonanywhere.com/static/icon-192.png" width="64" height="64" style="border-radius:14px;margin-bottom:12px;" />
            <h1 style="color:white;margin:0;font-size:24px;font-weight:800;letter-spacing:-0.5px;">Progressor</h1>
            <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">Train smarter. Recover better.</p>
        </div>
        <div style="padding:32px;background:#1a1d26;">
            <h2 style="color:#e8eaf0;margin:0 0 16px;font-size:20px;">Привет{', ' + name if name else ''}! 👋</h2>
            <p style="color:#8b92a8;line-height:1.6;margin:0 0 24px;">Ты почти готов начать тренироваться умнее. Подтверди свой email чтобы войти в Progressor.</p>
            <a href="{verify_url}" style="display:block;background:linear-gradient(135deg,#1a8a4a,#2ecc71);color:white;text-decoration:none;padding:14px 24px;border-radius:10px;font-weight:700;font-size:16px;text-align:center;">✅ Подтвердить email</a>
            <p style="color:#8b92a8;font-size:12px;margin:24px 0 0;text-align:center;">Если ты не регистрировался — просто проигнорируй это письмо.</p>
        </div>
    </div>
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
    logger.info(f"LOGIN user_id={user['id']} email={email}")
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
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE id=?", (session.get("user_id"),)).fetchone()
    conn.close()
    if not user:
        session.clear()
        abort(401, description="Пользователь не найден")


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
        SELECT u.id, u.email, u.name, u.age, u.gender, u.is_admin, u.is_verified, u.created_at,
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
    conn.execute("DELETE FROM exercises WHERE user_id=?", (user_id,))
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


@app.route("/measurements", methods=["GET"])
def get_measurements():
    require_auth()
    conn = get_db()
    rows = conn.execute("""
        SELECT log_date, chest_cm, waist_cm, hips_cm, shoulder_cm, bicep_cm, notes
        FROM body_measurements
        WHERE user_id = ? ORDER BY log_date DESC LIMIT 20
    """, (current_user_id(),)).fetchall()
    conn.close()
    return jsonify({"history": [dict(r) for r in rows]})

@app.route("/measurements", methods=["POST"])
def save_measurements():
    require_auth()
    data = request.get_json() or {}
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    conn = get_db()
    conn.execute("""
        INSERT INTO body_measurements (user_id, log_date, chest_cm, waist_cm, hips_cm, shoulder_cm, bicep_cm, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, log_date) DO UPDATE SET
            chest_cm = excluded.chest_cm,
            waist_cm = excluded.waist_cm,
            hips_cm = excluded.hips_cm,
            shoulder_cm = excluded.shoulder_cm,
            bicep_cm = excluded.bicep_cm,
            notes = excluded.notes
    """, (current_user_id(), date,
          data.get("chest_cm"), data.get("waist_cm"), data.get("hips_cm"),
          data.get("shoulder_cm"), data.get("bicep_cm"), data.get("notes")))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════
#  ДНИ И УПРАЖНЕНИЯ
# ══════════════════════════════════════════════
@app.route("/day/<int:day_id>")
def get_day(day_id):
    require_auth()
    uid = current_user_id()
    conn = get_db()
    cur = conn.cursor()
    # Дни — глобальные шаблоны, без фильтра по user
    day = cur.execute("SELECT id, name FROM day_templates WHERE id = ?", (day_id,)).fetchone()
    if not day:
        conn.close()
        abort(404, description="День не найден")
    # Упражнения — только личные копии пользователя
    exercises = cur.execute("""
        SELECT id, name, machine_model, plan_sets, plan_reps_range, default_weight, rest_seconds
        FROM exercises WHERE day_id = ? AND user_id = ? ORDER BY sort_order
    """, (day_id, uid)).fetchall()
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
    uid = current_user_id()
    conn = get_db()
    cur = conn.cursor()
    # Дни глобальные — проверяем без user_id
    day = cur.execute("SELECT id FROM day_templates WHERE id = ?", (data["day_id"],)).fetchone()
    if not day:
        conn.close()
        abort(400, description="Неверный day_id")

    for ex_log in data["exercises"]:
        # Упражнения — только из личной программы пользователя
        exercise = cur.execute(
            "SELECT id, default_weight FROM exercises WHERE id = ? AND day_id = ? AND user_id = ?",
            (ex_log["exercise_id"], data["day_id"], uid)
        ).fetchone()
        if not exercise:
            conn.close()
            abort(400, description=f"Упражнение {ex_log['exercise_id']} не относится к дню {data['day_id']}")

        # Защита от дублей (строгий user_id)
        cur.execute("DELETE FROM workout_log WHERE exercise_id = ? AND workout_date = ? AND user_id = ?",
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
            if s["reps"] < 0 or weight < 0:
                conn.close()
                abort(400, description="Вес и повторения не могут быть отрицательными")
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
    logger.info(f"WORKOUT_SAVED user_id={current_user_id()} date={data['date']} day={data['day_id']}")
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
          AND wl.user_id = ?
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
          AND wl.user_id = ?
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
              AND wl.user_id = ?
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
          AND wl.user_id = ?
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
    uid = current_user_id()
    conn = get_db()
    cur = conn.cursor()
    # ФИКС: добавлен AND user_id = ? — только свои записи
    cur.execute("""
        UPDATE workout_log SET weight = ?, reps = ?, difficulty = ?
        WHERE exercise_id IN (SELECT id FROM exercises WHERE name = ?)
          AND workout_date = ? AND set_number = ? AND user_id = ?
    """, (data["weight"], data["reps"], data.get("difficulty"),
          data["exercise_name"], data["workout_date"], data["set_number"], uid))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete-workout", methods=["POST"])
def delete_workout():
    require_auth()
    data = request.get_json()
    if not data or "workout_date" not in data:
        abort(400, description="Нет даты")
    uid = current_user_id()
    conn = get_db()
    conn.execute("DELETE FROM workout_log WHERE user_id = ? AND workout_date = ?", (uid, data["workout_date"]))
    conn.commit()
    conn.close()
    logger.info(f"WORKOUT_DELETED user_id={uid} date={data['workout_date']}")
    return jsonify({"status": "ok"})

@app.route("/exercise/<int:exercise_id>", methods=["PUT"])
def update_exercise(exercise_id):
    require_auth()
    data = request.get_json()
    if not data:
        abort(400, description="Нет данных для обновления")
    uid = current_user_id()
    conn = get_db()
    cur = conn.cursor()
    # Проверяем владельца упражнения
    ex = cur.execute("SELECT id FROM exercises WHERE id = ? AND user_id = ?", (exercise_id, uid)).fetchone()
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
    params.append(uid)
    cur.execute(f"UPDATE exercises SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
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
          AND wl.user_id = ?
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
    # Только упражнения текущего пользователя
    rows = cur.execute(
        "SELECT DISTINCT name FROM exercises WHERE user_id = ? ORDER BY name",
        (current_user_id(),)
    ).fetchall()
    conn.close()
    return jsonify({"names": [r["name"] for r in rows]})


@app.route("/stats-summary")
def stats_summary():
    require_auth()
    conn = get_db()
    cur = conn.cursor()
    uid = current_user_id()
    total = cur.execute(
        "SELECT COUNT(DISTINCT workout_date) FROM workout_log WHERE user_id = ?", (uid,)
    ).fetchone()[0]
    this_month = cur.execute("""
        SELECT COUNT(DISTINCT workout_date) FROM workout_log
        WHERE strftime('%Y-%m', workout_date) = strftime('%Y-%m', 'now')
          AND user_id = ?
    """, (uid,)).fetchone()[0]
    month_tonnage = cur.execute("""
        SELECT COALESCE(SUM(weight * reps), 0) FROM workout_log
        WHERE strftime('%Y-%m', workout_date) = strftime('%Y-%m', 'now') AND set_number > 0
          AND user_id = ?
    """, (uid,)).fetchone()[0]
    weeks = cur.execute("""
        SELECT DISTINCT strftime('%Y-%W', workout_date) as week
        FROM workout_log WHERE user_id = ? ORDER BY week DESC LIMIT 52
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
        FROM workout_log WHERE set_number > 0 AND user_id = ?
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
        WHERE wl.set_number > 0 AND wl.user_id = ?
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
        "" + output.getvalue(),
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
        WHERE user_id = ?
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
        WHERE user_id = ?
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
          AND wl.user_id = ?
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
          AND wl.user_id = ?
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
        AND wl.user_id = ?
        AND wl.id IN (
            SELECT MAX(id) FROM workout_log
            WHERE set_number > 0 AND difficulty IS NOT NULL AND difficulty != ''
              AND user_id = ?
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
    uid = current_user_id()

    # Фикс #4: дедупликация — если анализ уже был создан < 1 часа назад,
    # возвращаем кэш без повторного запроса к YandexGPT
    conn_dedup = get_db()
    recent = conn_dedup.execute("""
        SELECT recommendation_text FROM ai_recommendations
        WHERE user_id = ? AND created_at >= datetime('now', '-1 hour')
        ORDER BY created_at DESC LIMIT 1
    """, (uid,)).fetchone()
    conn_dedup.close()
    if recent:
        return jsonify({"status": "ok", "analysis": recent["recommendation_text"], "cached": True})

    data = request.get_json() or {}
    # Показатели восстановления от пользователя
    sleep = data.get("sleep", None)
    energy = data.get("energy", None)
    stress = data.get("stress", None)

    conn = get_db()
    cur = conn.cursor()

    # Последняя тренировка
    last_date_row = cur.execute("""
        SELECT MAX(workout_date) as last_date FROM workout_log
        WHERE set_number > 0 AND user_id = ?
    """, (uid,)).fetchone()
    last_date = last_date_row["last_date"] if last_date_row else None

    # Определяем day_id последней тренировки
    last_day_id = None
    if last_date:
        r = cur.execute("""
            SELECT e.day_id FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND wl.set_number > 0 AND wl.user_id = ?
            LIMIT 1
        """, (last_date, uid)).fetchone()
        if r:
            last_day_id = r["day_id"]

    # Данные последней тренировки
    last_sets = []
    last_dur_min = None
    if last_date:
        last_duration = cur.execute(
            "SELECT MAX(duration_seconds) as dur FROM workout_log WHERE workout_date = ? AND user_id = ?",
            (last_date, uid)
        ).fetchone()
        last_dur_min = round(last_duration["dur"] / 60) if last_duration and last_duration["dur"] else None
        last_sets = cur.execute("""
            SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND wl.set_number > 0
              AND wl.user_id = ?
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
              AND wl.user_id = ?
        """, (last_date, last_day_id, uid)).fetchone()
        prev_date = prev_date_row["prev_date"] if prev_date_row else None
        if prev_date:
            prev_sets = cur.execute("""
                SELECT e.name, wl.set_number, wl.weight, wl.reps, wl.difficulty
                FROM workout_log wl
                JOIN exercises e ON e.id = wl.exercise_id
                WHERE wl.workout_date = ? AND wl.set_number > 0
                  AND wl.user_id = ?
                ORDER BY e.sort_order, wl.set_number
            """, (prev_date, uid)).fetchall()

    # Тоннаж по неделям за 30 дней
    weekly = cur.execute("""
        SELECT strftime('%Y-%W', workout_date) as week, SUM(weight * reps) as tonnage
        FROM workout_log WHERE set_number > 0
        AND workout_date >= date('now', '-30 days')
        AND user_id = ?
        GROUP BY week ORDER BY week
    """, (uid,)).fetchall()

    # Макс веса по упражнениям
    records = cur.execute("""
        SELECT e.name, MAX(wl.weight) as max_weight
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.set_number > 0 AND wl.user_id = ?
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

    # Последние замеры тела
    conn4 = get_db()
    meas = conn4.execute("""
        SELECT log_date, chest_cm, waist_cm, hips_cm, bicep_cm
        FROM body_measurements WHERE user_id = ?
        ORDER BY log_date DESC LIMIT 2
    """, (uid,)).fetchall()
    conn4.close()
    if meas:
        last = meas[0]
        meas_str = f"Последние замеры ({last['log_date']}): "
        if last['chest_cm']: meas_str += f"грудь {last['chest_cm']} см, "
        if last['waist_cm']: meas_str += f"талия {last['waist_cm']} см, "
        if last['hips_cm']: meas_str += f"бёдра {last['hips_cm']} см, "
        if last['bicep_cm']: meas_str += f"бицепс {last['bicep_cm']} см. "
        profile_str += meas_str

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
            logger.info(f"AI_ANALYZE user_id={uid} date={last_date}")
            return jsonify({"status": "ok", "analysis": answer})

    except Exception as e:
        send_telegram(f"🔴 <b>Progressor AI Error</b>\n{str(e)}")
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
          AND wl.user_id = ?
        WHERE r.user_id = ?
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
          AND wl.user_id = ?
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
              AND wl.user_id = ?
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


@app.route("/progress-summary")
def progress_summary():
    require_auth()
    uid = current_user_id()
    conn = get_db()
    # Проверяем кэш
    cache = conn.execute(
        "SELECT summary_text, last_workout_date FROM progress_summary_cache WHERE user_id=?", (uid,)
    ).fetchone()
    last_workout = conn.execute(
        "SELECT MAX(workout_date) as d FROM workout_log WHERE user_id=? AND set_number>0", (uid,)
    ).fetchone()
    last_date = last_workout["d"] if last_workout else None
    if cache and cache["last_workout_date"] == last_date:
        conn.close()
        return jsonify({"status": "ok", "summary": cache["summary_text"], "cached": True})

    # Даты — 8 недель назад
    from datetime import date, timedelta
    eight_weeks_ago = (date.today() - timedelta(weeks=8)).isoformat()

    # Тренировки за 8 недель
    workouts = conn.execute("""
        SELECT COUNT(DISTINCT workout_date) as count,
               SUM(weight * reps) as total_tonnage,
               MAX(workout_date) as last_date,
               MIN(workout_date) as first_date
        FROM workout_log
        WHERE user_id = ? AND set_number > 0 AND workout_date >= ?
    """, (uid, eight_weeks_ago)).fetchone()

    # Прирост по упражнениям
    exercise_progress = conn.execute("""
        SELECT e.name,
               MIN(wl.weight) as start_weight,
               MAX(wl.weight) as max_weight,
               MAX(wl.weight) - MIN(wl.weight) as gain
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.user_id = ? AND wl.set_number > 0 AND wl.workout_date >= ?
        GROUP BY e.name
        HAVING COUNT(DISTINCT wl.workout_date) >= 2
        ORDER BY gain DESC
        LIMIT 5
    """, (uid, eight_weeks_ago)).fetchall()

    # Тоннаж первые 4 недели vs последние 4 недели
    four_weeks_ago = (date.today() - timedelta(weeks=4)).isoformat()
    tonnage_first = conn.execute("""
        SELECT COALESCE(SUM(weight * reps), 0) as t FROM workout_log
        WHERE user_id = ? AND set_number > 0
        AND workout_date >= ? AND workout_date < ?
    """, (uid, eight_weeks_ago, four_weeks_ago)).fetchone()["t"]
    tonnage_last = conn.execute("""
        SELECT COALESCE(SUM(weight * reps), 0) as t FROM workout_log
        WHERE user_id = ? AND set_number > 0 AND workout_date >= ?
    """, (uid, four_weeks_ago)).fetchone()["t"]

    # Вес тела — первое и последнее значение
    bw_first = conn.execute("""
        SELECT weight_kg FROM body_weight WHERE user_id = ?
        AND log_date >= ? ORDER BY log_date ASC LIMIT 1
    """, (uid, eight_weeks_ago)).fetchone()
    bw_last = conn.execute("""
        SELECT weight_kg FROM body_weight WHERE user_id = ?
        ORDER BY log_date DESC LIMIT 1
    """, (uid,)).fetchone()

    # Замеры — первые и последние
    meas_first = conn.execute("""
        SELECT * FROM body_measurements WHERE user_id = ?
        AND log_date >= ? ORDER BY log_date ASC LIMIT 1
    """, (uid, eight_weeks_ago)).fetchone()
    meas_last = conn.execute("""
        SELECT * FROM body_measurements WHERE user_id = ?
        ORDER BY log_date DESC LIMIT 1
    """, (uid,)).fetchone()

    # Профиль
    profile = conn.execute(
        "SELECT age, gender, weight_kg, height_cm, goal FROM users WHERE id=?", (uid,)
    ).fetchone()
    conn.close()

    # Формируем данные для AI
    profile_str = ""
    if profile:
        if profile["age"]: profile_str += f"Возраст: {profile['age']} лет. "
        if profile["gender"]: profile_str += f"Пол: {profile['gender']}. "
        if profile["height_cm"]: profile_str += f"Рост: {profile['height_cm']} см. "
        if profile["goal"]: profile_str += f"Цель: {profile['goal']}. "

    bw_change = ""
    if bw_first and bw_last:
        diff = round(bw_last["weight_kg"] - bw_first["weight_kg"], 1)
        sign = "+" if diff > 0 else ""
        bw_change = f"Вес тела: {bw_first['weight_kg']} → {bw_last['weight_kg']} кг ({sign}{diff} кг). "

    meas_change = ""
    if meas_first and meas_last:
        parts = []
        for field, name in [("waist_cm","талия"), ("chest_cm","грудь"), ("bicep_cm","бицепс")]:
            if meas_first[field] and meas_last[field]:
                diff = round(meas_last[field] - meas_first[field], 1)
                sign = "+" if diff > 0 else ""
                parts.append(f"{name}: {sign}{diff} см")
        if parts: meas_change = "Замеры: " + ", ".join(parts) + ". "

    ex_str = ""
    for r in exercise_progress:
        if r["gain"] > 0:
            ex_str += f"{r['name']}: +{r['gain']} кг. "

    tonnage_change = ""
    if tonnage_last > 0:
        if tonnage_first > 0:
            pct = round((tonnage_last - tonnage_first) / tonnage_first * 100)
            sign = "+" if pct > 0 else ""
            tonnage_change = f"Тоннаж: первые 4 нед {round(tonnage_first)} кг → последние 4 нед {round(tonnage_last)} кг ({sign}{pct}%). "
        else:
            tonnage_change = f"Тоннаж за последние 4 недели: {round(tonnage_last)} кг (данные за первые 4 нед отсутствуют). "

    prompt = f"""Ты — AI-тренер приложения Progressor. Составь краткий отчёт о прогрессе пользователя за последние 8 недель.

ПРОФИЛЬ: {profile_str}
ТРЕНИРОВКИ: {workouts['count'] if workouts else 0} тренировок за 8 недель ({workouts['first_date'] if workouts else '?'} — {workouts['last_date'] if workouts else '?'}).
{bw_change}{meas_change}{ex_str}{tonnage_change}

Ответ строго в формате:

**📊 Сводка прогресса за 8 недель**

**Индекс прогресса: X/100**
Одно предложение что означает этот индекс.

**Ключевые достижения:**
- 3-4 конкретных факта с цифрами

**Состав тела:**
- Изменение веса и замеров с интерпретацией

**Силовой прогресс:**
- Топ-3 упражнения с приростом

**Тоннаж:**
- Динамика за период

**Вывод AI:**
Один абзац — стал ли пользователь лучше, что работает, что требует внимания.

ВАЖНО: только факты из данных. Без слов "возможно", "может быть". Все цифры из данных."""

    try:
        import urllib.request, json as _json
        payload = _json.dumps({
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt",
            "completionOptions": {"stream": False, "temperature": 0.4, "maxTokens": 1500},
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
            # Сохраняем в кэш
            cache_conn = get_db()
            cache_conn.execute(
                "INSERT OR REPLACE INTO progress_summary_cache (user_id, summary_text, last_workout_date) VALUES (?, ?, ?)",
                (uid, answer, last_date)
            )
            cache_conn.execute(
                "INSERT INTO ai_analysis_history (user_id, summary_text) VALUES (?, ?)",
                (uid, answer)
            )
            cache_conn.commit()
            cache_conn.close()
            return jsonify({"status": "ok", "summary": answer, "cached": False, "data": {
                "workouts": workouts["count"] if workouts else 0,
                "bw_change": bw_change,
                "tonnage_change": tonnage_change
            }})
    except Exception as e:
        send_telegram(f"🔴 <b>Progressor Summary Error</b>\n{str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/prs")
def get_prs():
    require_auth()
    uid = current_user_id()
    conn = get_db()
    rows = conn.execute("""
        SELECT e.name, MAX(wl.weight) as weight,
               (SELECT wl2.workout_date FROM workout_log wl2
                WHERE wl2.user_id = wl.user_id AND wl2.exercise_id = wl.exercise_id
                AND wl2.weight = MAX(wl.weight) AND wl2.set_number > 0
                ORDER BY wl2.workout_date DESC LIMIT 1) as date
        FROM workout_log wl
        JOIN exercises e ON e.id = wl.exercise_id
        WHERE wl.user_id = ? AND wl.set_number > 0 AND wl.weight > 0
        GROUP BY wl.exercise_id
        ORDER BY weight DESC
    """, (uid,)).fetchall()
    conn.close()
    prs = [{"name": r["name"], "weight": r["weight"], "date": r["date"]} for r in rows]
    return jsonify({"status": "ok", "prs": prs})


@app.route("/achievements")
def get_achievements():
    require_auth()
    uid = current_user_id()
    conn = get_db()
    from datetime import date, timedelta
    from collections import defaultdict

    # ── Все даты тренировок ──────────────────────────────────────────────────
    dates = [r["workout_date"] for r in conn.execute(
        "SELECT DISTINCT workout_date FROM workout_log "
        "WHERE user_id=? AND set_number>0 ORDER BY workout_date", (uid,)
    ).fetchall()]
    total_workouts = len(dates)
    first_workout_date = dates[0] if dates else None

    def date_at(n):
        return dates[n - 1] if total_workouts >= n else None

    # ── Первый PR ────────────────────────────────────────────────────────────
    pr = conn.execute("""
        SELECT MIN(workout_date) as d FROM (
            SELECT exercise_id, workout_date, MAX(weight) as mw
            FROM workout_log WHERE user_id=? AND set_number>0
            GROUP BY exercise_id, workout_date
        ) t1 WHERE mw > (
            SELECT COALESCE(MAX(weight),0) FROM workout_log
            WHERE user_id=? AND exercise_id=t1.exercise_id
            AND workout_date < t1.workout_date AND set_number>0
        )
    """, (uid, uid)).fetchone()

    # ── Недельные стрики (Постоянство × 4 нед, Десятка × 10 нед) ────────────
    weeks_set = set()
    for d in dates:
        y, w, _ = date.fromisoformat(d).isocalendar()
        weeks_set.add((y, w))
    weeks = sorted(weeks_set)
    streak_4_date = None
    streak_10_date = None
    if weeks:
        streak = 1
        for i in range(1, len(weeks)):
            prev = date.fromisocalendar(weeks[i-1][0], weeks[i-1][1], 1)
            curr = date.fromisocalendar(weeks[i][0], weeks[i][1], 1)
            if (curr - prev).days == 7:
                streak += 1
                if streak >= 4 and not streak_4_date:
                    streak_4_date = curr.isoformat()
                if streak >= 10 and not streak_10_date:
                    streak_10_date = curr.isoformat()
                    break
            else:
                streak = 1

    # ── Рост объёма (+10% тоннажа) ───────────────────────────────────────────
    volume_date = None
    weekly_tons = conn.execute("""
        SELECT strftime('%Y-%W', workout_date) as week, SUM(weight*reps) as t
        FROM workout_log WHERE user_id=? AND set_number>0
        GROUP BY week ORDER BY week
    """, (uid,)).fetchall()
    if len(weekly_tons) >= 2:
        first_t = weekly_tons[0]["t"] or 0
        max_t = max(w["t"] or 0 for w in weekly_tons)
        if first_t > 0 and max_t >= first_t * 1.1:
            volume_date = dates[-1] if dates else None

    # ── Тяжеловес: 100 кг в любом упражнении ────────────────────────────────
    heavy = conn.execute(
        "SELECT MIN(workout_date) as d FROM workout_log "
        "WHERE user_id=? AND weight >= 100 AND set_number>0", (uid,)
    ).fetchone()

    # ── Полгода: 26 недель с первой тренировки ───────────────────────────────
    halfyear_date = None
    if first_workout_date:
        target = date.fromisoformat(first_workout_date) + timedelta(weeks=26)
        if date.today() >= target:
            halfyear_date = target.isoformat()

    # ── Прогрессор: прогресс в КАЖДОМ упражнении ────────────────────────────
    progresser_date = None
    total_ex_trained = conn.execute(
        "SELECT COUNT(DISTINCT exercise_id) FROM workout_log "
        "WHERE user_id=? AND set_number>0", (uid,)
    ).fetchone()[0]
    if total_ex_trained > 0:
        ex_with_pr = conn.execute("""
            SELECT COUNT(DISTINCT exercise_id) FROM (
                SELECT exercise_id, workout_date, MAX(weight) as mw
                FROM workout_log WHERE user_id=? AND set_number>0
                GROUP BY exercise_id, workout_date
            ) t1 WHERE mw > (
                SELECT COALESCE(MAX(weight),0) FROM workout_log
                WHERE user_id=? AND exercise_id=t1.exercise_id
                AND workout_date < t1.workout_date AND set_number>0
            )
        """, (uid, uid)).fetchone()[0]
        if ex_with_pr >= total_ex_trained:
            progresser_date = dates[-1] if dates else None

    # ── Двойной прогресс: вес ≥ 2× стартового в любом упражнении ────────────
    double_row = conn.execute("""
        SELECT MIN(wl.workout_date) as d
        FROM workout_log wl
        WHERE wl.user_id = ? AND wl.set_number > 0 AND wl.weight > 0
        AND wl.weight >= 2 * (
            SELECT w2.weight FROM workout_log w2
            WHERE w2.user_id = ? AND w2.exercise_id = wl.exercise_id
            AND w2.set_number > 0 AND w2.weight > 0
            ORDER BY w2.workout_date ASC, w2.id ASC LIMIT 1
        )
    """, (uid, uid)).fetchone()

    # ── Режим: самочувствие 7 дней подряд ───────────────────────────────────
    recovery_dates = [r["log_date"] for r in conn.execute(
        "SELECT DISTINCT log_date FROM recovery_log WHERE user_id=? ORDER BY log_date", (uid,)
    ).fetchall()]
    regime_date = None
    if len(recovery_dates) >= 7:
        for i in range(len(recovery_dates) - 6):
            d0 = date.fromisoformat(recovery_dates[i])
            d6 = date.fromisoformat(recovery_dates[i + 6])
            if (d6 - d0).days == 6:
                regime_date = recovery_dates[i + 6]
                break

    # ── Баланс: всегда ≥2 дня между тренировками (мин. 10 тренировок) ────────
    balance_date = None
    if total_workouts >= 10:
        all_ok = True
        for i in range(1, len(dates)):
            if (date.fromisoformat(dates[i]) - date.fromisoformat(dates[i-1])).days < 2:
                all_ok = False
                break
        if all_ok:
            balance_date = dates[-1]

    # ── Тоннаж нарастающим итогом (Локомотив 100к, Атлант 1М) ───────────────
    loco_date = None
    atlas_date = None
    cumulative = 0
    for row in conn.execute("""
        SELECT workout_date, SUM(weight * reps) as t
        FROM workout_log WHERE user_id=? AND set_number>0
        GROUP BY workout_date ORDER BY workout_date
    """, (uid,)).fetchall():
        cumulative += (row["t"] or 0)
        if loco_date is None and cumulative >= 100_000:
            loco_date = row["workout_date"]
        if atlas_date is None and cumulative >= 1_000_000:
            atlas_date = row["workout_date"]
            break

    # ── Замеры тела ──────────────────────────────────────────────────────────
    meas_rows = conn.execute(
        "SELECT log_date FROM body_measurements WHERE user_id=? ORDER BY log_date", (uid,)
    ).fetchall()
    meas_first = meas_rows[0]["log_date"] if meas_rows else None
    antrop_date = meas_rows[9]["log_date"] if len(meas_rows) >= 10 else None

    # ── Вес тела ─────────────────────────────────────────────────────────────
    bw_rows = conn.execute(
        "SELECT log_date, weight_kg FROM body_weight WHERE user_id=? ORDER BY log_date", (uid,)
    ).fetchall()
    bw_first = bw_rows[0]["log_date"] if bw_rows else None
    disc_date = bw_rows[29]["log_date"] if len(bw_rows) >= 30 else None

    # Метаморфоза: изменение веса на 5 кг
    morph_date = None
    if len(bw_rows) >= 2:
        first_bw = bw_rows[0]["weight_kg"]
        for row in bw_rows[1:]:
            if abs(row["weight_kg"] - first_bw) >= 5:
                morph_date = row["log_date"]
                break

    # ── Стабильность: 3 мес. подряд по 8+ тренировок ────────────────────────
    stability_date = None
    if dates:
        monthly = defaultdict(int)
        monthly_last = {}
        for d in dates:
            mk = d[:7]
            monthly[mk] += 1
            monthly_last[mk] = d
        sorted_months = sorted(monthly.keys())
        for i in range(len(sorted_months) - 2):
            m0, m1, m2 = sorted_months[i], sorted_months[i+1], sorted_months[i+2]
            dm0 = date.fromisoformat(m0 + "-01")
            dm1 = date.fromisoformat(m1 + "-01")
            dm2 = date.fromisoformat(m2 + "-01")
            consec = (dm1.year*12+dm1.month == dm0.year*12+dm0.month+1 and
                      dm2.year*12+dm2.month == dm1.year*12+dm1.month+1)
            if consec and monthly[m0] >= 8 and monthly[m1] >= 8 and monthly[m2] >= 8:
                stability_date = monthly_last[m2]
                break

    # ── AI Follower ───────────────────────────────────────────────────────────
    ai = conn.execute(
        "SELECT MIN(created_at) as d FROM ai_recommendations WHERE user_id=?", (uid,)
    ).fetchone()

    conn.close()

    badges = [
        # Тренировки — количество
        {"id": "first_workout",   "icon": "🏋️", "name": "Первая тренировка",    "desc": "Первая тренировка в Progressor",           "earned": bool(first_workout_date), "date": first_workout_date},
        {"id": "progress_champ",  "icon": "🏆",  "name": "Чемпион прогресса",    "desc": "10 тренировок выполнено",                  "earned": total_workouts >= 10,     "date": date_at(10)},
        {"id": "silver",          "icon": "🥈",  "name": "Серебро",              "desc": "50 тренировок выполнено",                  "earned": total_workouts >= 50,     "date": date_at(50)},
        {"id": "century",         "icon": "💯",  "name": "Сотня",                "desc": "100 тренировок выполнено",                 "earned": total_workouts >= 100,    "date": date_at(100)},
        {"id": "gold",            "icon": "🥇",  "name": "Золото",               "desc": "200 тренировок выполнено",                 "earned": total_workouts >= 200,    "date": date_at(200)},
        # Прогресс
        {"id": "pr_hunter",       "icon": "🎯",  "name": "Охотник за рекордами", "desc": "Первый личный рекорд по весу",             "earned": bool(pr and pr["d"]),     "date": pr["d"] if pr else None},
        {"id": "progresser",      "icon": "💪",  "name": "Прогрессор",           "desc": "Прогресс в каждом упражнении",             "earned": bool(progresser_date),    "date": progresser_date},
        {"id": "double_progress", "icon": "⚡",  "name": "Двойной прогресс",     "desc": "Вес в упражнении вырос в 2 раза",          "earned": bool(double_row and double_row["d"]), "date": double_row["d"] if double_row else None},
        {"id": "heavy",           "icon": "🏋️", "name": "Тяжеловес",            "desc": "100 кг в любом упражнении",                "earned": bool(heavy and heavy["d"]), "date": heavy["d"] if heavy else None},
        # Стабильность
        {"id": "consistency",     "icon": "🔥",  "name": "Постоянство",          "desc": "4 недели тренировок подряд",               "earned": bool(streak_4_date),      "date": streak_4_date},
        {"id": "ten_weeks",       "icon": "🔟",  "name": "Десятка",              "desc": "10 недель тренировок подряд",              "earned": bool(streak_10_date),     "date": streak_10_date},
        {"id": "halfyear",        "icon": "📅",  "name": "Полгода",              "desc": "6 месяцев в приложении",                   "earned": bool(halfyear_date),      "date": halfyear_date},
        {"id": "stability",       "icon": "📈",  "name": "Стабильность",         "desc": "3 месяца подряд по 8+ тренировок",         "earned": bool(stability_date),     "date": stability_date},
        {"id": "balance",         "icon": "🧘",  "name": "Баланс",               "desc": "Всегда отдыхаешь между тренировками",      "earned": bool(balance_date),       "date": balance_date},
        # Объём и тоннаж
        {"id": "volume_builder",  "icon": "📊",  "name": "Рост объёма",          "desc": "Тоннаж вырос на 10%+",                    "earned": bool(volume_date),        "date": volume_date},
        {"id": "locomotive",      "icon": "🚂",  "name": "Локомотив",            "desc": "100 000 кг суммарного тоннажа",            "earned": bool(loco_date),          "date": loco_date},
        {"id": "atlas",           "icon": "🌍",  "name": "Атлант",               "desc": "1 000 000 кг суммарного тоннажа",          "earned": bool(atlas_date),         "date": atlas_date},
        # Здоровье и тело
        {"id": "regime",          "icon": "😴",  "name": "Режим",                "desc": "Самочувствие 7 дней подряд",               "earned": bool(regime_date),        "date": regime_date},
        {"id": "weight_tracker",  "icon": "⚖️", "name": "Контроль веса",         "desc": "Первая запись веса тела",                  "earned": bool(bw_first),           "date": bw_first},
        {"id": "discipline",      "icon": "⚖️", "name": "Дисциплина",            "desc": "30 записей веса тела",                     "earned": bool(disc_date),          "date": disc_date},
        {"id": "meas_tracker",    "icon": "📏",  "name": "Замеры тела",          "desc": "Первые замеры тела",                       "earned": bool(meas_first),         "date": meas_first},
        {"id": "anthropolog",     "icon": "📐",  "name": "Антрополог",           "desc": "10 записей замеров тела",                  "earned": bool(antrop_date),        "date": antrop_date},
        {"id": "metamorph",       "icon": "🧬",  "name": "Метаморфоза",          "desc": "Вес тела изменился на 5 кг",               "earned": bool(morph_date),         "date": morph_date},
        # AI
        {"id": "ai_follower",     "icon": "🧠",  "name": "Следую AI",            "desc": "Первый AI-анализ получен",                 "earned": bool(ai and ai["d"]),     "date": str(ai["d"])[:10] if ai and ai["d"] else None},
    ]

    earned = sum(1 for b in badges if b["earned"])
    score = round(earned / len(badges) * 100)

    return jsonify({"status": "ok", "badges": badges, "score": score, "earned": earned, "total": len(badges)})


@app.route("/admin/verify-user/<int:user_id>", methods=["POST"])
def admin_verify_user(user_id):
    require_admin()
    conn = get_db()
    conn.execute("UPDATE users SET is_verified=1, verify_token=NULL WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete-account", methods=["POST"])
def delete_account():
    require_auth()
    uid = current_user_id()
    conn = get_db()
    # Проверяем что не единственный админ
    admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
    is_admin = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()["is_admin"]
    if is_admin and admin_count <= 1:
        conn.close()
        return jsonify({"status": "error", "message": "Нельзя удалить единственного администратора"}), 400
    conn.execute("DELETE FROM workout_log WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM recovery_log WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM body_weight WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM body_measurements WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM ai_recommendations WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM exercises WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    session.clear()
    return jsonify({"status": "ok"})

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
        logger.error(f"RESTORE_ERROR user_id={current_user_id()} {str(e)}")
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

    # Упражнения с прогрессирующими весами — поиск по имени и user_id
    day1_exercises = [
        ("Тяга верхнего блока",             [32.5, 35, 37.5, 40]),
        ("Жим плечами (дельтоидный)",        [30, 32.5, 35, 37.5]),
        ("Вертикальный жим грудью",           [32.5, 35, 37.5, 40]),
        ("Обратная бабочка (задние дельты)",  [15, 17.5, 17.5, 20]),
        ("Сгибание рук (бицепс)",             [17.5, 20, 20, 20]),
        ("Пресс",                             [0, 5, 5, 5]),
    ]
    day2_exercises = [
        ("Разгибание ног",                    [30, 32.5, 35, 37.5]),
        ("Сгибание ног",                      [25, 27.5, 30, 32.5]),
        ("Горизонтальный жим ногами",         [60, 65, 70, 75]),
        ("Приводящая машина",                 [30, 32.5, 35, 35]),
        ("Отводящая машина",                  [35, 37.5, 40, 40]),
    ]
    day3_exercises = [
        ("Жим плечами (дельтоидный)",         [30, 32.5, 35, 37.5]),
        ("Тяга верхнего блока (узкий хват)",  [35, 37.5, 40, 40]),
        ("Вертикальный жим грудью",           [35, 37.5, 40, 40]),
        ("Тяга блока к поясу",                [30, 32.5, 35, 35]),
        ("Разгибание на трицепс",             [10, 12.5, 15, 15]),
        ("Пресс",                             [0, 5, 5, 5]),
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

        for ex_name, base_weights in exercises:
            # Ищем упражнение по имени в личной программе пользователя
            ex = cur.execute(
                "SELECT id, plan_sets FROM exercises WHERE name = ? AND user_id = ? LIMIT 1",
                (ex_name, uid)
            ).fetchone()
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
                """, (uid, ex["id"], workout_date.isoformat(), set_num, weight, reps, diff))

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
        WHERE wl.set_number > 0 AND wl.user_id = ?
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
                    WHERE workout_date = ? AND user_id = ?) as duration_seconds
            FROM workout_log wl
            JOIN exercises e ON e.id = wl.exercise_id
            WHERE wl.workout_date = ? AND e.day_id = ? AND wl.set_number > 0
              AND wl.user_id = ?
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

@app.errorhandler(500)
def handle_500(e):
    logger.error(f"500 ERROR: {str(e)}")
    send_telegram(f"🔴 <b>Progressor 500</b>\n{str(e)}")
    return jsonify({"status": "error", "message": "Внутренняя ошибка"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    if hasattr(e, 'code') and e.code < 500:
        return e
    send_telegram(f"🔴 <b>Progressor Exception</b>\n{type(e).__name__}: {str(e)}")
    return jsonify({"status": "error", "message": str(e)}), 500