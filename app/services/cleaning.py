from datetime import datetime
from typing import Any

import csv
import io
import re

REQUIRED_COLUMNS = {
    "txn_id",
    "date",
    "merchant",
    "amount",
    "currency",
    "status",
    "category",
    "account_id",
    "notes",
}


def parse_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file is empty or has no header row")

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}
        rows.append(row)
    return rows, list(reader.fieldnames or [])


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("empty date")

    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {value}")


def parse_amount(value: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", value.replace("$", "").strip())
    if not cleaned:
        raise ValueError("empty amount")
    return float(cleaned)


def clean_transactions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for row in rows:
        try:
            record = {
                "txn_id": row["txn_id"] or None,
                "date": normalize_date(row["date"]),
                "merchant": row["merchant"].strip(),
                "amount": parse_amount(row["amount"]),
                "currency": row["currency"].strip().upper(),
                "status": row["status"].strip().upper(),
                "category": row["category"].strip(),
                "account_id": row["account_id"].strip(),
                "notes": row["notes"].strip() or None,
                "needs_llm_category": not row["category"].strip(),
            }
        except (ValueError, KeyError):
            continue

        if not record["merchant"] or not record["account_id"]:
            continue

        dedup_key = (
            record["txn_id"],
            record["date"],
            record["merchant"],
            record["amount"],
            record["currency"],
            record["status"],
            record["category"] or "",
            record["account_id"],
            record["notes"] or "",
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if not record["category"]:
            record["category"] = "Uncategorised"

        cleaned.append(record)

    return cleaned
