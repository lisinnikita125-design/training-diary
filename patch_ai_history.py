#!/usr/bin/env python3
"""
Патч для истории AI-анализов:
  1. database.py — добавить таблицу ai_analysis_history
  2. main.py     — INSERT в историю при каждом /ai-analyze
  3. main.py     — новый маршрут /ai-history (последние 10 анализов)
"""

import re

DB_PATH   = '/home/NikitaLisin/database.py'
MAIN_PATH = '/home/NikitaLisin/main.py'

# ═══════════════════════════════════════════════════════════════════════════════
# 1. database.py — добавить таблицу ai_analysis_history перед conn.commit()
# ═══════════════════════════════════════════════════════════════════════════════

with open(DB_PATH, encoding='utf-8') as f:
    db_src = f.read()

NEW_TABLE = '''
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

    '''

# Вставляем перед conn.commit()
if 'ai_analysis_history' in db_src:
    print('ℹ️  ai_analysis_history уже есть в database.py, пропускаем')
else:
    db_src = db_src.replace(
        '    conn.commit()\n    conn.close()',
        NEW_TABLE + '    conn.commit()\n    conn.close()',
        1  # только первая замена (в init_db)
    )
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        f.write(db_src)
    print('✅ database.py — таблица ai_analysis_history добавлена')

# ═══════════════════════════════════════════════════════════════════════════════
# 2. main.py — сохранять анализ в историю при /ai-analyze
# ═══════════════════════════════════════════════════════════════════════════════

with open(MAIN_PATH, encoding='utf-8') as f:
    main_src = f.read()

# Находим строку сохранения в cache и добавляем INSERT в историю рядом
OLD_CACHE_BLOCK = '''            cache_conn = get_db()
            cache_conn.execute(
                "INSERT OR REPLACE INTO progress_summary_cache (user_id, summary_text, last_workout_date) VALUES (?, ?, ?)",
                (uid, answer, last_date)
            )
            cache_conn.commit()
            cache_conn.close()'''

NEW_CACHE_BLOCK = '''            cache_conn = get_db()
            cache_conn.execute(
                "INSERT OR REPLACE INTO progress_summary_cache (user_id, summary_text, last_workout_date) VALUES (?, ?, ?)",
                (uid, answer, last_date)
            )
            cache_conn.execute(
                "INSERT INTO ai_analysis_history (user_id, summary_text) VALUES (?, ?)",
                (uid, answer)
            )
            cache_conn.commit()
            cache_conn.close()'''

if OLD_CACHE_BLOCK in main_src:
    main_src = main_src.replace(OLD_CACHE_BLOCK, NEW_CACHE_BLOCK, 1)
    print('✅ main.py — INSERT в ai_analysis_history добавлен')
elif 'ai_analysis_history' in main_src:
    print('ℹ️  INSERT в ai_analysis_history уже есть в main.py')
else:
    print('❌ Не найден блок сохранения кэша — проверь main.py вручную')

# ═══════════════════════════════════════════════════════════════════════════════
# 3. main.py — добавить маршрут /ai-history перед /achievements
# ═══════════════════════════════════════════════════════════════════════════════

NEW_HISTORY_ROUTE = '''@app.route("/ai-history")
def get_ai_history():
    require_auth()
    uid = current_user_id()
    conn = get_db()
    rows = conn.execute("""
        SELECT id, summary_text,
               strftime('%d.%m.%Y %H:%M', created_at, 'localtime') as formatted_date,
               created_at
        FROM ai_analysis_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (uid,)).fetchall()
    conn.close()
    history = [
        {
            "id": r["id"],
            "text": r["summary_text"],
            "date": r["formatted_date"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]
    return jsonify({"status": "ok", "history": history})


'''

if '/ai-history' in main_src:
    print('ℹ️  /ai-history уже есть в main.py, пропускаем')
else:
    # Вставляем перед маршрутом /achievements
    ach_marker = '@app.route("/achievements")\ndef get_achievements():'
    if ach_marker in main_src:
        main_src = main_src.replace(ach_marker, NEW_HISTORY_ROUTE + ach_marker, 1)
        print('✅ main.py — маршрут /ai-history добавлен')
    else:
        print('❌ Маркер /achievements не найден — /ai-history не добавлен')

# ═══════════════════════════════════════════════════════════════════════════════
# 4. main.py — маршрут /prs (личные рекорды по весу)
# ═══════════════════════════════════════════════════════════════════════════════

NEW_PRS_ROUTE = '''@app.route("/prs")
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


'''

if '/prs' in main_src:
    print('ℹ️  /prs уже есть в main.py, пропускаем')
else:
    ach_marker = '@app.route("/achievements")\ndef get_achievements():'
    if ach_marker in main_src:
        main_src = main_src.replace(ach_marker, NEW_PRS_ROUTE + ach_marker, 1)
        print('✅ main.py — маршрут /prs добавлен')
    else:
        print('❌ Маркер /achievements не найден — /prs не добавлен')

with open(MAIN_PATH, 'w', encoding='utf-8') as f:
    f.write(main_src)

# ═══════════════════════════════════════════════════════════════════════════════
# Итоговая проверка
# ═══════════════════════════════════════════════════════════════════════════════
print()
with open(MAIN_PATH, encoding='utf-8') as f:
    final = f.read()
with open(DB_PATH, encoding='utf-8') as f:
    final_db = f.read()

checks = [
    (final_db, 'ai_analysis_history',                         'DB: таблица ai_analysis_history'),
    (final,    'INSERT INTO ai_analysis_history',              'main: INSERT в историю'),
    (final,    '@app.route("/ai-history")',                    'main: маршрут /ai-history'),
    (final,    '@app.route("/prs")',                           'main: маршрут /prs'),
    (final,    'ORDER BY created_at DESC',                     'main: сортировка истории'),
]
all_ok = True
for src_text, needle, label in checks:
    found = needle in src_text
    print(f'{"✅" if found else "❌"} {label}')
    if not found:
        all_ok = False
print()
print('✅ Всё готово' if all_ok else '❌ Есть ошибки')
