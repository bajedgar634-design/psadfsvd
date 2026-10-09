"""
Проект: «Учёт личных финансов»
Консольное приложение на Python (только стандартная библиотека).

Возможности:
  1. Добавление доходов и расходов
  2. Просмотр всех операций
  3. Статистика по категориям (с текстовой диаграммой)
  4. Удаление операции
  5. Экспорт в CSV
Данные хранятся в базе SQLite (файл finance.db).
"""

from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

DB_NAME = "finance.db"
CATEGORIES = ["Еда", "Транспорт", "Развлечения", "Учёба", "Здоровье", "Зарплата", "Другое"]
KINDS = ("доход", "расход")


# ---------- Работа с базой данных ----------

@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Контекстный менеджер: гарантирует commit при успехе и rollback при ошибке."""
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('доход', 'расход')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                note TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)")


def add_record(rec_date: str, kind: str, category: str, amount: float, note: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO records (date, kind, category, amount, note) VALUES (?, ?, ?, ?, ?)",
            (rec_date, kind, category, amount, note),
        )


def get_records() -> list[tuple]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, date, kind, category, amount, note FROM records ORDER BY date, id"
        ).fetchall()


def delete_record(rec_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM records WHERE id = ?", (rec_id,))
        return cur.rowcount > 0


# ---------- Ввод данных с проверкой ----------

def input_amount() -> float:
    while True:
        text = input("Сумма: ").replace(",", ".").strip()
        try:
            value = float(text)
        except ValueError:
            print("  Ошибка: введите число.")
            continue
        if value != value or value in (float("inf"), float("-inf")):
            print("  Ошибка: число некорректно.")
            continue
        if value <= 0:
            print("  Ошибка: сумма должна быть положительной.")
            continue
        return round(value, 2)


def input_date() -> str:
    """Поддерживает пустой ввод, формат ГГГГ-ММ-ДД и относительные даты."""
    today = date.today()
    while True:
        text = input("Дата (ГГГГ-ММ-ДД, Enter = сегодня, -1 = вчера): ").strip()
        if not text:
            return today.isoformat()
        # относительные даты: -N дней
        if text.startswith("-") and text[1:].isdigit():
            return (today - timedelta(days=int(text[1:]))).isoformat()
        try:
            return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            print("  Ошибка: неверный формат даты.")


def choose_category() -> str:
    for i, name in enumerate(CATEGORIES, 1):
        print(f"  {i}. {name}")
    while True:
        text = input("Номер категории: ").strip()
        if text.isdigit() and 1 <= int(text) <= len(CATEGORIES):
            return CATEGORIES[int(text) - 1]
        print("  Ошибка: выберите номер из списка.")


def choose_kind() -> str:
    while True:
        text = input("Тип (1 - доход, 2 - расход): ").strip()
        if text == "1":
            return "доход"
        if text == "2":
            return "расход"
        print("  Ошибка: введите 1 или 2.")


# ---------- Пункты меню ----------

def menu_add() -> None:
    print("\n--- Новая операция ---")
    kind = choose_kind()
    rec_date = input_date()
    category = choose_category()
    amount = input_amount()
    note = input("Комментарий (необязательно): ").strip()
    add_record(rec_date, kind, category, amount, note)
    print("Операция добавлена!")


def menu_list() -> None:
    records = get_records()
    print("\n--- Все операции ---")
    if not records:
        print("Пока пусто.")
        return

    header = f"{'ID':<5}{'Дата':<12}{'Тип':<9}{'Категория':<15}{'Сумма':>12}  Комментарий"
    print(header)
    print("-" * len(header))
    for rec_id, d, kind, cat, amount, note in records:
        sign = "+" if kind == "доход" else "-"
        print(f"{rec_id:<5}{d:<12}{kind:<9}{cat:<15}{sign}{amount:>11.2f}  {note or ''}")


def menu_stats() -> None:
    records = get_records()
    print("\n--- Статистика ---")
    if not records:
        print("Нет данных.")
        return

    income = sum(r[4] for r in records if r[2] == "доход")
    expense = sum(r[4] for r in records if r[2] == "расход")
    print(f"Доходы:  {income:10.2f}")
    print(f"Расходы: {expense:10.2f}")
    print(f"Баланс:  {income - expense:10.2f}")

    # Расходы по категориям
    by_cat: dict[str, float] = {}
    for _, _, kind, cat, amount, _ in records:
        if kind == "расход":
            by_cat[cat] = by_cat.get(cat, 0) + amount

    if by_cat:
        print("\nРасходы по категориям:")
        max_total = max(by_cat.values())
        for cat, total in sorted(by_cat.items(), key=lambda x: -x[1]):
            share = (total / expense * 100) if expense else 0.0
            bar_len = int(total / max_total * 30) if max_total else 0
            bar = "█" * bar_len
            print(f"  {cat:<13}{total:9.2f} {share:5.1f}% {bar}")

    # Опционально: статистика по месяцам
    print("\nДоходы/расходы по месяцам:")
    by_month: dict[str, list[float]] = {}
    for _, d, kind, _, amount, _ in records:
        month = d[:7]
        pair = by_month.setdefault(month, [0.0, 0.0])
        pair[0 if kind == "доход" else 1] += amount
    for month in sorted(by_month):
        inc, exp = by_month[month]
        print(f"  {month}:  +{inc:8.2f}  -{exp:8.2f}  = {inc - exp:8.2f}")


def menu_delete() -> None:
    records = get_records()
    if not records:
        print("\n--- Удаление ---\nПока нечего удалять.")
        return
    menu_list()
    text = input("\nID для удаления (Enter - отмена): ").strip()
    if not text:
        print("Отменено.")
        return
    if not text.isdigit():
        print("Ошибка: ID должен быть числом.")
        return
    print("Удалено." if delete_record(int(text)) else "Запись не найдена.")


def menu_export() -> None:
    records = get_records()
    if not records:
        print("Нечего экспортировать.")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = Path(f"finance_export_{stamp}.csv")
    with filename.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ID", "Дата", "Тип", "Категория", "Сумма", "Комментарий"])
        writer.writerows(records)
    print(f"Экспортировано записей: {len(records)} -> {filename.resolve()}")


# ---------- Точка входа ----------

MENU = (
    "\n===== УЧЁТ ФИНАНСОВ =====\n"
    "1. Добавить операцию\n"
    "2. Показать все операции\n"
    "3. Статистика\n"
    "4. Удалить операцию\n"
    "5. Экспорт в CSV\n"
    "0. Выход"
)


def main() -> None:
    init_db()
    actions = {
        "1": menu_add,
        "2": menu_list,
        "3": menu_stats,
        "4": menu_delete,
        "5": menu_export,
    }
    while True:
        print(MENU)
        choice = input("Выбор: ").strip()
        if choice == "0":
            print("До свидания!")
            break
        action = actions.get(choice)
        if action:
            action()
        else:
            print("Неверный пункт меню.")


if __name__ == "__main__":
    main()