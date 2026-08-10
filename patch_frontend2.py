#!/usr/bin/env python3
"""
Патч index.html (Task #11):
  1. Новая вкладка «Достижения» (бейджи + PR-рекорды) перед «Мой прогресс»
  2. «Мой прогресс» — убрать автозагрузку, добавить кнопку «Запустить AI-анализ»
                       и блок истории последних анализов
  3. Иконка вкладки «Мой прогресс» остаётся, но содержимое меняется
"""

import re

PATH = '/home/NikitaLisin/static/index.html'

with open(PATH, encoding='utf-8') as f:
    html = f.read()

original_len = len(html)

# ══════════════════════════════════════════════════════════════════════════════
# ШАБЛОНЫ ДЛЯ ПОИСКА — найдём нужные якоря в существующем коде
# ══════════════════════════════════════════════════════════════════════════════

# Шаг 1: найти якорь вкладки «Мой прогресс» в навбаре
# Обычно это что-то вроде: <button onclick="showTab('progress')" ...>
# Ищем кнопку nav с «прогресс» (регистронезависимо)
nav_btn_match = re.search(
    r"(<button[^>]+showTab\('progress'\)[^>]*>.*?</button>)",
    html, re.IGNORECASE | re.DOTALL
)
if not nav_btn_match:
    # Попробуем другой вариант с data-tab
    nav_btn_match = re.search(
        r"(<button[^>]+data-tab=['\"]progress['\"][^>]*>.*?</button>)",
        html, re.IGNORECASE | re.DOTALL
    )

# Шаг 2: найти контейнер вкладки прогресса
# Ищем div с id="tab-progress" или class="tab" и data-tab="progress"
tab_div_match = re.search(
    r'(<div[^>]+id=["\']tab-progress["\'][^>]*>)',
    html, re.IGNORECASE
)

print('Поиск якорей:')
print(f'  nav кнопка "progress": {"✅ найдена" if nav_btn_match else "❌ не найдена"}')
if nav_btn_match:
    print(f'    → {nav_btn_match.group(0)[:120]}')
print(f'  tab div "progress": {"✅ найден" if tab_div_match else "❌ не найден"}')
if tab_div_match:
    print(f'    → {tab_div_match.group(0)[:120]}')

# ══════════════════════════════════════════════════════════════════════════════
# ОПРЕДЕЛЯЕМ ТАКТИКУ по тому, что нашли
# ══════════════════════════════════════════════════════════════════════════════

changes = 0

# ── А. Добавляем кнопку «Достижения» в навбар ─────────────────────────────
if nav_btn_match:
    old_nav_btn = nav_btn_match.group(0)
    # Новая кнопка для «Достижения» — вставим ПЕРЕД кнопкой progress
    achievements_nav_btn = old_nav_btn\
        .replace("showTab('progress')", "showTab('achievements')")\
        .replace("progress", "achievements")\
        .replace("Мой прогресс", "Достижения")\
        .replace("📊", "🏆")\
        .replace("📈", "🏆")
    # Убираем дублирование — если уже нет кнопки achievements
    if "showTab('achievements')" not in html:
        html = html.replace(old_nav_btn, achievements_nav_btn + '\n          ' + old_nav_btn, 1)
        print('\n✅ Навбар: кнопка «Достижения» добавлена')
        changes += 1
    else:
        print('\nℹ️  Кнопка achievements уже есть в навбаре')
else:
    print('\n⚠️  Кнопка progress не найдена автоматически.')
    print('   Ищем вкладки другим способом...')
    # Попробуем найти по тексту «Мой прогресс»
    alt_match = re.search(r'(<button[^>]*>[\s\S]{0,30}Мой прогресс[\s\S]{0,30}</button>)', html)
    if alt_match:
        old_btn = alt_match.group(0)
        new_btn = re.sub(r"showTab\('(\w+)'\)", "showTab('achievements')", old_btn)
        new_btn = new_btn.replace('Мой прогресс', 'Достижения')
        if "showTab('achievements')" not in html:
            html = html.replace(old_btn, new_btn + '\n          ' + old_btn, 1)
            print('✅ Навбар: кнопка «Достижения» добавлена (альт. метод)')
            changes += 1

# ── Б. Добавляем div#tab-achievements после div#tab-progress ──────────────
if 'id="tab-achievements"' not in html and "id='tab-achievements'" not in html:
    # Найдём закрывающий тег div вкладки progress, используя регулярку
    # Вставим новый div после блока прогресса
    # Ищем конец блока progress: </div><!-- /tab-progress --> или просто ищем следующий div того же уровня

    # Надёжнее: найдём функцию renderAchievements/loadAchievements в JS
    # и вставим новый div перед скриптами

    # Находим место перед </body> или перед <script>
    NEW_ACHIEVEMENTS_TAB = '''
<div id="tab-achievements" class="tab" style="display:none">
  <h2 style="margin-bottom:16px">🏆 Достижения</h2>
  <div id="achievements-score-bar" style="margin-bottom:20px"></div>
  <div id="achievements-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px"></div>

  <h2 style="margin:28px 0 16px">📋 Личные рекорды</h2>
  <div id="prs-list"></div>
</div>
'''
    # Вставляем перед закрывающим </main> или перед первым <script>
    if '</main>' in html:
        html = html.replace('</main>', NEW_ACHIEVEMENTS_TAB + '</main>', 1)
        print('✅ div#tab-achievements добавлен (перед </main>)')
        changes += 1
    else:
        # Вставляем после последнего </div> перед <script>
        script_pos = html.find('<script')
        if script_pos != -1:
            html = html[:script_pos] + NEW_ACHIEVEMENTS_TAB + '\n' + html[script_pos:]
            print('✅ div#tab-achievements добавлен (перед <script>)')
            changes += 1
        else:
            print('❌ Не удалось найти место для вставки tab-achievements')
else:
    print('ℹ️  div#tab-achievements уже существует')

# ── В. Рефакторим вкладку «Мой прогресс»: убираем auto-load, добавляем кнопку + историю
# Ищем div#tab-progress и меняем его содержимое
if tab_div_match:
    # Найдём весь блок вкладки прогресса методом подсчёта скобок
    start = html.find(tab_div_match.group(0))
    if start != -1:
        # Ищем блок summary внутри вкладки
        # Добавляем кнопку запуска и блок истории, если их ещё нет
        if 'ai-trigger-btn' not in html:
            # Найдём div#progress-summary или div#ai-summary внутри tab-progress
            summary_match = re.search(
                r'(<div[^>]+id=["\'](?:progress-summary|ai-summary)["\'][^>]*>)',
                html
            )
            if summary_match:
                old_summary_open = summary_match.group(0)
                new_summary_open = (
                    '<div style="margin-bottom:20px">\n'
                    '    <button id="ai-trigger-btn" onclick="triggerAiAnalysis()" '
                    'class="btn-primary" style="width:100%;padding:14px;font-size:16px">'
                    '🤖 Запустить AI-анализ</button>\n'
                    '  </div>\n  ' + old_summary_open
                )
                html = html.replace(old_summary_open, new_summary_open, 1)
                print('✅ Кнопка «Запустить AI-анализ» добавлена')
                changes += 1
            else:
                print('ℹ️  div#progress-summary/ai-summary не найден — кнопка не добавлена')

# ── Г. Добавляем блок истории анализов в tab-progress ─────────────────────
if 'ai-history-list' not in html:
    # Ищем конец содержимого tab-progress — вставим перед </div><!-- /tab-progress -->
    # или найдём закрывающий тег после id="tab-progress"
    AI_HISTORY_BLOCK = '''
  <div style="margin-top:28px">
    <h3 style="margin-bottom:12px">📜 История анализов</h3>
    <div id="ai-history-list" style="display:flex;flex-direction:column;gap:12px">
      <p style="color:var(--muted);font-size:14px">История загружается...</p>
    </div>
  </div>
'''
    # Вставляем перед закрывающим тегом блока summary
    # Ищем id="progress-summary-result" или аналог
    result_match = re.search(r'id=["\'](?:summary-result|progress-result|ai-result)["\']', html)
    if result_match:
        # Вставляем после этого блока
        pos = result_match.end()
        # Найдём закрывающий </div> этого элемента
        close_pos = html.find('</div>', pos)
        if close_pos != -1:
            html = html[:close_pos+6] + AI_HISTORY_BLOCK + html[close_pos+6:]
            print('✅ Блок истории AI добавлен')
            changes += 1
    else:
        # Запасной вариант: ищем конец tab-progress по паттерну комментария или следующей вкладке
        # Найдём div#tab-achievements который мы только что добавили и вставим перед ним
        hist_insert = html.find('<div id="tab-achievements"')
        if hist_insert != -1:
            # Ищем предыдущий </div>
            prev_div = html.rfind('</div>', 0, hist_insert)
            if prev_div != -1:
                html = html[:prev_div] + AI_HISTORY_BLOCK + html[prev_div:]
                print('✅ Блок истории AI добавлен (альт. метод)')
                changes += 1
else:
    print('ℹ️  ai-history-list уже существует')

# ══════════════════════════════════════════════════════════════════════════════
# JAVASCRIPT: добавляем функции для новой вкладки
# ══════════════════════════════════════════════════════════════════════════════

NEW_JS = '''
// ── Достижения (tab-achievements) ──────────────────────────────────────────
async function loadAchievementsTab() {
  const grid = document.getElementById('achievements-grid');
  const scoreBar = document.getElementById('achievements-score-bar');
  if (!grid) return;
  grid.innerHTML = '<p style="color:var(--muted);font-size:14px">Загрузка...</p>';
  try {
    const r = await fetch('/achievements');
    const d = await r.json();
    if (d.status !== 'ok') throw new Error(d.message || 'Ошибка');

    scoreBar.innerHTML = `
      <div style="background:var(--card-bg);border-radius:12px;padding:14px 16px;display:flex;align-items:center;gap:12px;border:1px solid var(--border)">
        <div style="font-size:28px;font-weight:700;color:var(--accent)">${d.earned}</div>
        <div>
          <div style="font-size:13px;color:var(--muted)">получено из ${d.total}</div>
          <div style="height:6px;background:var(--border);border-radius:4px;margin-top:6px;width:200px">
            <div style="height:100%;width:${d.score}%;background:var(--accent);border-radius:4px;transition:width .4s"></div>
          </div>
        </div>
        <div style="margin-left:auto;font-size:20px;font-weight:700;color:var(--accent)">${d.score}%</div>
      </div>`;

    grid.innerHTML = d.badges.map(b => `
      <div style="background:var(--card-bg);border-radius:12px;padding:14px;text-align:center;
           border:2px solid ${b.earned ? 'var(--accent)' : 'var(--border)'};
           opacity:${b.earned ? '1' : '0.45'};transition:opacity .2s">
        <div style="font-size:32px;margin-bottom:6px">${b.icon}</div>
        <div style="font-weight:600;font-size:13px;margin-bottom:4px">${b.name}</div>
        <div style="font-size:11px;color:var(--muted);line-height:1.3">${b.desc}</div>
        ${b.earned && b.date ? `<div style="font-size:10px;color:var(--accent);margin-top:6px">${b.date}</div>` : ''}
      </div>`).join('');
  } catch(e) {
    grid.innerHTML = `<p style="color:var(--error)">Ошибка: ${e.message}</p>`;
  }

  // Личные рекорды
  const prsList = document.getElementById('prs-list');
  if (prsList) {
    try {
      const r2 = await fetch('/prs');
      const d2 = await r2.json();
      if (d2.status === 'ok' && d2.prs && d2.prs.length) {
        prsList.innerHTML = '<div style="display:flex;flex-direction:column;gap:8px">' +
          d2.prs.map(p => `
            <div style="background:var(--card-bg);border-radius:10px;padding:12px 14px;
                 border:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
              <div>
                <div style="font-weight:600;font-size:14px">${p.name}</div>
                <div style="font-size:12px;color:var(--muted)">${p.date}</div>
              </div>
              <div style="font-size:18px;font-weight:700;color:var(--accent)">${p.weight} кг</div>
            </div>`).join('') + '</div>';
      } else {
        prsList.innerHTML = '<p style="color:var(--muted);font-size:14px">Нет рекордов</p>';
      }
    } catch(e) {
      prsList.innerHTML = '<p style="color:var(--muted);font-size:14px">Рекорды недоступны</p>';
    }
  }
}

// ── AI-анализ по кнопке ─────────────────────────────────────────────────────
async function triggerAiAnalysis() {
  const btn = document.getElementById('ai-trigger-btn');
  const summaryEl = document.getElementById('progress-summary') ||
                    document.getElementById('ai-summary') ||
                    document.getElementById('summary-result') ||
                    document.getElementById('progress-result') ||
                    document.getElementById('ai-result');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Анализирую...'; }
  try {
    const r = await fetch('/ai-analyze', { method: 'POST' });
    const d = await r.json();
    if (d.status === 'ok') {
      if (summaryEl) summaryEl.innerHTML = marked ? marked.parse(d.analysis || d.summary || '') : (d.analysis || d.summary || '');
      await loadAiHistory();
    } else {
      showToast(d.message || 'Ошибка AI', true);
    }
  } catch(e) {
    showToast('Ошибка соединения', true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🤖 Запустить AI-анализ'; }
  }
}

// ── История AI-анализов ─────────────────────────────────────────────────────
async function loadAiHistory() {
  const listEl = document.getElementById('ai-history-list');
  if (!listEl) return;
  try {
    const r = await fetch('/ai-history');
    const d = await r.json();
    if (d.status !== 'ok' || !d.history.length) {
      listEl.innerHTML = '<p style="color:var(--muted);font-size:14px">История анализов пуста</p>';
      return;
    }
    listEl.innerHTML = d.history.map((h, i) => `
      <details style="background:var(--card-bg);border:1px solid var(--border);border-radius:10px;overflow:hidden" ${i===0?'open':''}>
        <summary style="padding:12px 16px;cursor:pointer;font-weight:600;font-size:14px;list-style:none;display:flex;justify-content:space-between">
          <span>📊 ${h.date}</span>
          <span style="font-size:12px;color:var(--muted);font-weight:400">${i===0?'последний':''}</span>
        </summary>
        <div style="padding:0 16px 14px;font-size:13px;line-height:1.6;color:var(--text)">
          ${typeof marked !== 'undefined' ? marked.parse(h.text) : h.text.replace(/\\n/g,'<br>')}
        </div>
      </details>`).join('');
  } catch(e) {
    listEl.innerHTML = '<p style="color:var(--muted);font-size:14px">Ошибка загрузки истории</p>';
  }
}
// ── Хук на переключение вкладок ────────────────────────────────────────────
'''

# Вставляем JS перед закрывающим </script> в конце файла
# Ищем последний </script>
last_script_close = html.rfind('</script>')
if last_script_close != -1:
    if 'loadAchievementsTab' not in html:
        html = html[:last_script_close] + NEW_JS + html[last_script_close:]
        print('✅ JS-функции добавлены')
        changes += 1
    else:
        print('ℹ️  JS-функции уже есть')
else:
    print('❌ Не найден </script>')

# ── Д. Добавляем вызов loadAchievementsTab() в showTab ────────────────────
# Ищем функцию showTab и добавляем кейс для achievements
if 'achievements' not in html or "case 'achievements'" not in html:
    # Ищем паттерн включения вкладки progress
    show_progress_match = re.search(
        r"(case 'progress'[^:]*:|if\s*\(\s*tab\s*===?\s*['\"]progress['\"])",
        html
    )
    if show_progress_match:
        # Ищем вызов функции загрузки progress внутри этого кейса
        load_fn_match = re.search(
            r'(load(?:Progress|Summary|ProgressSummary|AiSummary)\(\))',
            html[show_progress_match.start():show_progress_match.start()+500]
        )
        if load_fn_match:
            old_load_call = load_fn_match.group(0)
            # В tab-progress: убираем автозагрузку AI, добавляем loadAiHistory()
            html = html.replace(
                old_load_call,
                'loadAiHistory()',
                1
            )
            print(f'✅ showTab(progress): {old_load_call} → loadAiHistory()')
            changes += 1

    # Добавляем кейс для achievements
    if "showTab('achievements')" in html or 'tab-achievements' in html:
        # Ищем функцию showTab целиком
        show_tab_fn = re.search(
            r'(function showTab\s*\([^)]*\)\s*\{)',
            html
        )
        if show_tab_fn and 'loadAchievementsTab' not in html[show_tab_fn.start():show_tab_fn.start()+600]:
            # Вставим в начало тела функции
            old_fn_open = show_tab_fn.group(0)
            html = html.replace(
                old_fn_open,
                old_fn_open + "\n  if (tab === 'achievements') { loadAchievementsTab(); }",
                1
            )
            print("✅ showTab: if (tab==='achievements') добавлен")
            changes += 1

# ══════════════════════════════════════════════════════════════════════════════
# Сохраняем
# ══════════════════════════════════════════════════════════════════════════════
if html != open(PATH, encoding='utf-8').read():
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ Записано {len(html)} байт → {PATH}')
    print(f'   Изменений применено: {changes}')
else:
    print('\n⚠️  Файл не изменился — возможно все патчи уже были применены')

# ── Финальная проверка ────────────────────────────────────────────────────
print()
checks = [
    ('tab-achievements',        'div#tab-achievements'),
    ('loadAchievementsTab',     'JS: loadAchievementsTab()'),
    ('triggerAiAnalysis',       'JS: triggerAiAnalysis()'),
    ('loadAiHistory',           'JS: loadAiHistory()'),
    ('ai-history-list',         'HTML: блок истории'),
    ('ai-trigger-btn',          'HTML: кнопка AI'),
    ('/ai-history',             'JS: fetch /ai-history'),
    ('achievements-grid',       'HTML: сетка бейджей'),
]
with open(PATH, encoding='utf-8') as f:
    final = f.read()

all_ok = True
for needle, label in checks:
    found = needle in final
    print(f'{"✅" if found else "❌"} {label}')
    if not found:
        all_ok = False

print()
print('✅ Фронтенд готов' if all_ok else '❌ Есть незакрытые пункты — проверь выше')
