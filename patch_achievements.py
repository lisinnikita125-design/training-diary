#!/usr/bin/env python3
"""
Патч main.py: расширенные достижения — 24 бейджа вместо 8.

Новые бейджи:
  🥈 Серебро          — 50 тренировок
  💯 Сотня            — 100 тренировок
  🥇 Золото           — 200 тренировок
  🔟 Десятка          — 10 недель подряд
  🏋️ Тяжеловес       — 100 кг в любом упражнении
  📅 Полгода          — 26 недель с первой тренировки
  💪 Прогрессор       — прогресс в каждом упражнении
  ⚡ Двойной прогресс — вес в 2 раза выше стартового
  😴 Режим            — самочувствие 7 дней подряд
  🧘 Баланс           — всегда отдых между тренировками (≥2 дней)
  🚂 Локомотив        — 100 000 кг суммарного тоннажа
  🌍 Атлант           — 1 000 000 кг суммарного тоннажа
  📐 Антрополог       — 10 записей замеров тела
  ⚖️ Дисциплина       — 30 записей веса тела
  📈 Стабильность     — 3 месяца подряд по 8+ тренировок
  🧬 Метаморфоза      — вес тела изменился на 5 кг
"""

PATH = '/home/NikitaLisin/main.py'

NEW_FUNC = '''@app.route("/achievements")
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

'''

START_MARKER = '@app.route("/achievements")\ndef get_achievements():'
END_MARKER   = '@app.route("/admin/verify-user/<int:user_id>", methods=["POST"])'

with open(PATH, encoding='utf-8') as f:
    src = f.read()

start_idx = src.find(START_MARKER)
end_idx   = src.find(END_MARKER)

if start_idx == -1:
    print("❌ Маркер начала не найден: @app.route('/achievements')")
    exit(1)
if end_idx == -1:
    print("❌ Маркер конца не найден: /admin/verify-user")
    exit(1)

new_src = src[:start_idx] + NEW_FUNC + '\n' + src[end_idx:]

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(new_src)

# Проверка
checks = [
    ('Серебро',          'Серебро 50 тренировок'),
    ('Золото',           'Золото 200 тренировок'),
    ('Тяжеловес',        'Тяжеловес 100 кг'),
    ('Локомотив',        'Локомотив 100к'),
    ('Атлант',           'Атлант 1М'),
    ('Метаморфоза',      'Метаморфоза 5 кг'),
    ('Стабильность',     'Стабильность 3 мес'),
    ('progresser_date',  'Прогрессор'),
    ('double_row',       'Двойной прогресс'),
    ('regime_date',      'Режим 7 дней'),
    ('balance_date',     'Баланс'),
    ('halfyear_date',    'Полгода'),
    ('"total": len(badges)', 'JSON total'),
]
print()
all_ok = True
for needle, label in checks:
    found = needle in new_src
    print(f'{"✅" if found else "❌"} {label}')
    if not found:
        all_ok = False

badge_count = new_src.count('"id":')
print(f'\nБейджей в источнике: ~{badge_count}')
print(f'\n✅ Записано {len(new_src)} байт → {PATH}' if all_ok else '\n❌ Есть ошибки, проверь вывод выше')
