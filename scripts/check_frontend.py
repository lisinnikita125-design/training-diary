"""
Структурные проверки статики, которые раньше делались руками перед мержем:

- баланс <div> / </div> в index.html;
- атрибуты без пробела между ними (id="x"style=...);
- синтаксис встроенных <script> и sw.js через `node --check` (если node установлен).

Запуск: python3 scripts/check_frontend.py  (код выхода 1 при ошибках)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "static", "index.html")
SW_JS = os.path.join(REPO_ROOT, "static", "sw.js")

# Закрывающая кавычка значения сразу же переходит в имя следующего атрибута.
GLUED_ATTR_RE = re.compile(r'"[A-Za-z][A-Za-z0-9_:-]*="')
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def check_div_balance(html):
    opened = len(re.findall(r"<div\b", html))
    closed = html.count("</div>")
    if opened != closed:
        return [f"index.html: <div> открыто {opened}, закрыто {closed}"]
    return []


def check_glued_attrs(html):
    errors = []
    for m in GLUED_ATTR_RE.finditer(html):
        line = html.count("\n", 0, m.start()) + 1
        errors.append(f"index.html:{line}: атрибуты без пробела: {m.group(0)}")
    return errors


def node_check(source, label):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = f.name
    try:
        proc = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    finally:
        os.remove(path)
    if proc.returncode != 0:
        return [f"{label}: синтаксическая ошибка JS\n{proc.stderr.strip()}"]
    return []


def check_js_syntax(html):
    errors = []
    for i, m in enumerate(INLINE_SCRIPT_RE.finditer(html), start=1):
        if m.group(1).strip():
            errors += node_check(m.group(1), f"index.html <script> #{i}")
    with open(SW_JS, encoding="utf-8") as f:
        errors += node_check(f.read(), "sw.js")
    return errors


def run_checks(html, with_node):
    errors = check_div_balance(html) + check_glued_attrs(html)
    if with_node:
        errors += check_js_syntax(html)
    return errors


def main():
    with open(INDEX_HTML, encoding="utf-8") as f:
        html = f.read()
    with_node = shutil.which("node") is not None
    if not with_node:
        print("WARN: node не найден, проверка синтаксиса JS пропущена")
    errors = run_checks(html, with_node)
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        return 1
    print("FRONTEND_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
