#!/usr/bin/env python3
"""
Патч index.html:
  Bug #2  — PR banner: 5000ms → 3000ms
  Bug #5  — pull-to-refresh iOS: overscroll-behavior: none
  Bug #6  — таймер: globalTimer = null после завершения
  Bug #7  — мелкий текст: +1px к ключевым размерам
"""
 
PATH = '/home/NikitaLisin/static/index.html'
 
with open(PATH, encoding='utf-8') as f:
    html = f.read()
 
original = html  # для сравнения в конце
 
# ── Bug #5: pull-to-refresh ──────────────────────────────────────────────────
# Добавляем overscroll-behavior: none в body
html = html.replace(
    "body { font-family:'Inter','Helvetica Neue',Arial,sans-serif; max-width:860px; margin:0 auto; padding:12px; background:var(--bg); color:var(--text); transition:background .2s,color .2s; }",
    "body { font-family:'Inter','Helvetica Neue',Arial,sans-serif; max-width:860px; margin:0 auto; padding:12px; background:var(--bg); color:var(--text); transition:background .2s,color .2s; overscroll-behavior: none; }"
)
 
# ── Bug #2: PR banner timeout ────────────────────────────────────────────────
html = html.replace(
    '}, 5000); }  // ══════════════════════════════════════════════',
    '}, 3000); }  // ══════════════════════════════════════════════'
)
# Запасной вариант если нет лишних пробелов
if '}, 5000);' in html:
    import re
    # Заменяем только в showPRBanner (prBannerTimer = setTimeout)
    html = re.sub(
        r'(prBannerTimer\s*=\s*setTimeout\s*\([^)]+\}\s*,\s*)5000(\s*\))',
        r'\g<1>3000\2',
        html
    )
 
# ── Bug #6: globalTimer = null после завершения таймера ─────────────────────
# Главная причина: autoStartTimer видит globalTimer !== null и не запускает таймер
html = html.replace(
    'if (remaining <= 0) {\n            clearInterval(globalTimer.interval);\n            displayEl.textContent',
    'if (remaining <= 0) {\n            clearInterval(globalTimer.interval);\n            globalTimer = null;\n            displayEl.textContent'
)
 
# ── Bug #7: шрифты ──────────────────────────────────────────────────────────
replacements = [
    # Таблица упражнений
    ('font-size:13px; }',   'font-size:14px; }'),   # .ex-name и другие 13px → 14px
    ('font-size:12px; }',   'font-size:13px; }'),   # .ex-model
    # 11px → 12px (prev-info, skip-badge)
    ('font-size:11px;',     'font-size:12px;'),
    # difficulty input
    ('difficulty-input { width:86px; padding:5px 6px; font-size:13px;',
     'difficulty-input { width:86px; padding:5px 6px; font-size:14px;'),
]
 
for old, new in replacements:
    count = html.count(old)
    html = html.replace(old, new)
    print(f'  font: "{old}" → "{new}" ({count} замен)')
 
# ── Проверка ─────────────────────────────────────────────────────────────────
checks = [
    ('overscroll-behavior: none',  'Bug #5 pull-to-refresh'),
    ('globalTimer = null;\n            displayEl.textContent', 'Bug #6 timer null'),
    ('}, 3000)',                    'Bug #2 PR banner 3000ms'),
]
 
print()
ok = True
for needle, label in checks:
    found = needle in html
    status = '✅' if found else '❌ НЕ НАЙДЕНО'
    print(f'{status}  {label}')
    if not found:
        ok = False
 
if html == original:
    print('\n⚠️  Файл не изменился — проверь строки выше')
else:
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write(html)