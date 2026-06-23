"""Разовый расчёт "общей" цены номенклатуры на основе уже загруженных цен
клиник в clinic_prices. Для каждой позиции берёт самую частую цену среди
клиник, у которых она задана, и проставляет её в nomenclature.price —
тем самым общий прайс становится осмысленным дефолтом, а реальные отличия
по клиникам остаются исключениями в clinic_prices.
"""
import os
import sqlite3
from collections import Counter, defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "dental_lab.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    by_item = defaultdict(list)
    for r in conn.execute("SELECT nomenclature_id, price FROM clinic_prices"):
        by_item[r["nomenclature_id"]].append(r["price"])

    updated = 0
    for nom_id, prices in by_item.items():
        base_price = Counter(prices).most_common(1)[0][0]
        conn.execute("UPDATE nomenclature SET price=? WHERE id=?", (base_price, nom_id))
        updated += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM nomenclature").fetchone()[0]
    print(f"Позиций с известной ценой у клиник: {len(by_item)} / {total}")
    print(f"Обновлено base-цен в nomenclature: {updated}")
    conn.close()


if __name__ == "__main__":
    main()
