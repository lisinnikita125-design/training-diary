#!/usr/bin/env python3
"""
Патч index.html (fix):
  — Добавить кнопку «Запустить AI-анализ» в начало div#tab-progress
  — Убрать автозагрузку AI при переходе на вкладку (заменить на loadAiHistory)
"""

PATH = '/home/NikitaLisin/static/index.html'

with open(PATH, encoding='utf-8') as f:
    html = f.read()

changes = 0

# ── 1. Кнопка «Запустить AI-анализ» сразу после открывающего тега tab-progress
TAB_OPEN = '<div id="tab-progress" class="hidden">'
BUTTON_BLOCK = '''<div id="tab-progress" class="hidden">
  <div style="margin-bottom:20px">
    <button id="ai-trigger-btn" onclick="triggerAiAnalysis()"
      style="width:100%;padding:14px;font-size:16px;font-weight:600;
             background:var(--accent);color:#fff;border:none;border-radius:10px;cursor:pointer">
      🤖 Запустить AI-анализ
    </button>
  </div>'''

if 'ai-trigger-btn' in html and '<button id="ai-trigger-btn"' in html:
    print('ℹ️  Кнопка ai-trigger-btn уже есть как HTML-элемент')
elif TAB_OPEN in html:
    html = html.replace(TAB_OPEN, BUTTON_BLOCK, 1)
    print('✅ Кнопка «Запустить AI-анализ» добавлена в tab-progress')
    changes += 1
else:
    # Попробуем без class="hidden"
    import re
    m = re.search(r'<div[^>]+id=["\']tab-progress["\'][^>]*>', html)
    if m:
        old = m.group(0)
        new = old + '\n  <div style="margin-bottom:20px"><button id="ai-trigger-btn" onclick="triggerAiAnalysis()" style="width:100%;padding:14px;font-size:16px;font-weight:600;background:var(--accent);color:#fff;border:none;border-radius:10px;cursor:pointer">🤖 Запустить AI-анализ</button></div>'
        html = html.replace(old, new, 1)
        print('✅ Кнопка добавлена (авто-метод)')
        changes += 1
    else:
        print('❌ div#tab-progress не найден')

# ── 2. Заменяем автозагрузку AI в showTab('progress') на loadAiHistory()
# Ищем вызов функции типа loadProgress/loadSummary/loadProgressSummary в showTab
import re

# Находим тело showTab и ищем в нём вызовы которые грузят AI
patterns_to_replace = [
    'loadProgressSummary()',
    'loadProgress()',
    'loadSummary()',
    'loadAISummary()',
    'loadAiSummary()',
    'fetchProgressSummary()',
]

replaced_autoload = False
for old_call in patterns_to_replace:
    if old_call in html:
        # Убедимся что это внутри блока case 'progress' или if tab === 'progress'
        # Просто делаем замену — если функция одна, это безопасно
        html = html.replace(old_call, 'loadAiHistory()', 1)
        print(f'✅ Автозагрузка: {old_call} → loadAiHistory()')
        replaced_autoload = True
        changes += 1
        break

if not replaced_autoload:
    print("ℹ️  Функция автозагрузки не найдена (возможно уже заменена или называется иначе)")
    # Покажем что вызывается при переходе на progress
    m = re.search(r"['\"]progress['\"][\s\S]{0,300}", html)
    if m:
        snippet = m.group(0)[:200].replace('\n', ' ')
        print(f'   Контекст вокруг "progress": {snippet}')

# ── Сохраняем ─────────────────────────────────────────────────────────────────
with open(PATH, 'w', encoding='utf-8') as f:
    f.write(html)

# ── Проверка ──────────────────────────────────────────────────────────────────
print()
with open(PATH, encoding='utf-8') as f:
    final = f.read()

checks = [
    ('<button id="ai-trigger-btn"', 'HTML кнопка ai-trigger-btn'),
    ('triggerAiAnalysis',           'JS: triggerAiAnalysis вызов'),
    ('loadAiHistory',               'loadAiHistory в showTab'),
]
all_ok = True
for needle, label in checks:
    found = needle in final
    print(f'{"✅" if found else "❌"} {label}')
    if not found:
        all_ok = False

print(f'\n{"✅ Готово" if all_ok else "⚠️  Есть незакрытые пункты"} (изменений: {changes})')
