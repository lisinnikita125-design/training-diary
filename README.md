# Progressor — Training Diary

> Дневник силовых тренировок с аналитикой прогресса.
> **Train smarter. Recover better.**

## 🚀 Demo
https://nikitalisin.pythonanywhere.com

## ✨ Возможности
- 6 вкладок: Тренировка, История, Прогресс, Сравнение, Статистика, Достижения
- Индекс готовности и индекс прогресса
- Вес тела и замеры с графиками
- PWA — устанавливается на iPhone

## 🛠 Стек
Flask · SQLite · Chart.js · PWA

## 🚀 Запуск локально
```bash
git clone https://github.com/lisinnikita125-design/training-diary.git
cd training-diary
pip install -r requirements.txt

# Создать config.py с секретным ключом сессий (обязательно, приложение не запустится без него)
# и локальным адресом: из APP_URL строятся ссылки-приглашения, по умолчанию он указывает на прод
echo "SECRET_KEY = '$(python3 -c 'import secrets; print(secrets.token_hex(32))')'" > config.py
echo "APP_URL = 'http://127.0.0.1:5000'" >> config.py

python3 database.py
python3 main.py
```
Приложение поднимется на http://127.0.0.1:5000/static/index.html

### Первый администратор
Регистрация работает только по приглашению, а приглашения создаёт администратор, поэтому
первого администратора в пустой базе нужно завести вручную (после `python3 database.py`,
email и пароль замените на свои):
```bash
python3 - <<'EOF'
from database import get_db, seed_user
from werkzeug.security import generate_password_hash
conn = get_db()
cur = conn.execute(
    "INSERT INTO users (email, password_hash, name, is_verified, is_admin, consent_pdn_at, consent_transfer_at) "
    "VALUES (?, ?, ?, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    ("admin@example.com", generate_password_hash("change-me"), "Admin"))
conn.commit()
seed_user(cur.lastrowid)
EOF
```
Дальше: войти этим аккаунтом → ⚙️ в шапке → «Настройки аккаунта» → «Админ» →
«Пригласить подопечного» и открыть полученную ссылку, чтобы зарегистрировать остальных пользователей.

## ✅ Тесты и проверки
Те же проверки запускает GitHub Actions на каждый push (`.github/workflows/ci.yml`):
```bash
pip install -r requirements-dev.txt
ruff check                          # ошибки уровня pyflakes в Python-коде
python3 scripts/check_frontend.py   # баланс <div>, склеенные атрибуты, синтаксис JS (нужен node)
pytest                              # тесты на временной базе, локальные config.py и training.db не трогаются
```

## 💾 Бэкап базы
`scripts/backup_db.py` снимает копию `training.db` через sqlite backup API (безопасно при
работающем приложении), проверяет её `PRAGMA integrity_check`, сжимает и складывает в
`db_backups/` (хранит 14 последних). На PythonAnywhere: вкладка **Tasks** → ежедневная задача
```bash
python3 /home/NikitaLisin/scripts/backup_db.py
```
Восстановление: Disable веб-приложения на вкладке Web, затем
`gunzip -c db_backups/training_ГГГГ-ММ-ДД_ЧЧММ.db.gz > training.db` и Enable.
Копии лежат на том же сервере: от поломки базы и ошибочного удаления спасают,
от потери аккаунта — нет, поэтому иногда стоит скачивать свежую копию себе.
