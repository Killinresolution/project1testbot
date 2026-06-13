"""
Запусти перед git push: python check_before_push.py
Проверяет, что секретные данные не попадут на GitHub.
"""
import sys
import re
import pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = pathlib.Path(__file__).parent
GITIGNORE = BASE / ".gitignore"

SENSITIVE_FILES = [".env", "ezra_bot.db", "*.db", "*.sqlite"]
TOKEN_PATTERN = re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}", re.MULTILINE)

ok = True


def check(label: str, passed: bool, detail: str = ""):
    global ok
    icon = "✅" if passed else "❌"
    print(f"  {icon}  {label}" + (f" — {detail}" if detail else ""))
    if not passed:
        ok = False


print("\n🔍 Проверка перед git push\n")

# 1. Есть ли .gitignore
check(".gitignore существует", GITIGNORE.exists())

if GITIGNORE.exists():
    content = GITIGNORE.read_text(encoding="utf-8")
    check(".env прописан в .gitignore", ".env" in content)
    check("*.db прописан в .gitignore", "*.db" in content)
    check("__pycache__ прописан в .gitignore", "__pycache__" in content)

# 2. Проверить, что .env существует локально (значит, был создан из примера)
check(".env существует локально", (BASE / ".env").exists(),
      "если нет — создай из .env.example")

# 3. Проверить, что .env.example НЕ содержит реального токена
example = BASE / ".env.example"
if example.exists():
    text = example.read_text(encoding="utf-8")
    has_real_token = bool(TOKEN_PATTERN.search(text))
    check(".env.example не содержит реального токена", not has_real_token,
          "в .env.example должна быть заглушка, не настоящий токен")

# 4. Проверить, что в .py файлах нет хардкода токена
print()
py_files = list(BASE.rglob("*.py"))
found_token = False
for f in py_files:
    if "__pycache__" in str(f):
        continue
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
        if TOKEN_PATTERN.search(text):
            check(f"Токен в {f.name}", False, f"найден в {f.relative_to(BASE)}")
            found_token = True
    except Exception:
        pass
if not found_token:
    check("Токен не захардкожен в .py файлах", True)

# 5. Предупреждение про .db файлы
db_files = list(BASE.glob("*.db")) + list(BASE.glob("*.sqlite"))
if db_files:
    names = ", ".join(f.name for f in db_files)
    print(f"\n  ⚠️  Найдены файлы БД: {names}")
    print("      Они исключены через .gitignore — в git не попадут.\n")

# Итог
print()
if ok:
    print("🟢 Всё в порядке — можно делать git push!\n")
else:
    print("🔴 Найдены проблемы — исправь их перед git push!\n")
