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
pip install flask werkzeug

# Создать config.py с секретным ключом сессий (обязательно, приложение не запустится без него)
echo "SECRET_KEY = '$(python3 -c 'import secrets; print(secrets.token_hex(32))')'" > config.py

python3 database.py
python3 main.py
```
Приложение поднимется на http://127.0.0.1:5000
