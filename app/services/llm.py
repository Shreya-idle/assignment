import json
import logging
import time
from typing import Any

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

VALID_CATEGORIES = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Cash Withdrawal",
    "Entertainment",
    "Other",
]

MERCHANT_CATEGORY_HINTS = {
    "swiggy": "Food",
    "zomato": "Food",
    "flipkart": "Shopping",
    "amazon": "Shopping",
    "irctc": "Travel",
    "makemytrip": "Travel",
    "ola": "Transport",
    "jio recharge": "Utilities",
    "hdfc atm": "Cash Withdrawal",
    "bookmyshow": "Entertainment",
}


def _configure_gemini() -> bool:
    if not settings.gemini_api_key:
        return False
    genai.configure(api_key=settings.gemini_api_key)
    return True


def _call_with_retry(prompt: str, max_retries: int = 3) -> tuple[str | None, bool]:
    if not _configure_gemini():
        return None, True

    model = genai.GenerativeModel(settings.llm_model)
    delay = 1.0

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
            return text.strip(), False
        except Exception as exc:
            logger.warning("LLM call failed (attempt %s): %s", attempt + 1, exc)
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
    return None, True


def _heuristic_category(merchant: str) -> str:
    merchant_lower = merchant.lower()
    for key, category in MERCHANT_CATEGORY_HINTS.items():
        if key in merchant_lower:
            return category
    return "Other"


def classify_categories_batch(
    transactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    pending = [t for t in transactions if t.get("needs_llm_category")]
    if not pending:
        return transactions, None, False

    batch_payload = [
        {
            "index": i,
            "merchant": t["merchant"],
            "amount": t["amount"],
            "currency": t["currency"],
            "notes": t.get("notes"),
        }
        for i, t in enumerate(pending)
    ]

    prompt = f"""Classify each transaction into exactly one category.
Valid categories: {', '.join(VALID_CATEGORIES)}

Return ONLY valid JSON array like:
[{{"index": 0, "category": "Food"}}, ...]

Transactions:
{json.dumps(batch_payload, indent=2)}
"""

    raw_response, failed = _call_with_retry(prompt)
    if failed or not raw_response:
        for txn in pending:
            txn["llm_category"] = _heuristic_category(txn["merchant"])
            txn["category"] = txn["llm_category"]
            txn["llm_failed"] = True
            txn["llm_raw_response"] = None
        return transactions, None, True

    try:
        parsed = json.loads(raw_response)
        mapping = {item["index"]: item["category"] for item in parsed}
        for i, txn in enumerate(pending):
            category = mapping.get(i, "Other")
            if category not in VALID_CATEGORIES:
                category = "Other"
            txn["llm_category"] = category
            txn["category"] = category
            txn["llm_failed"] = False
            txn["llm_raw_response"] = raw_response
        return transactions, raw_response, False
    except (json.JSONDecodeError, KeyError, TypeError):
        for txn in pending:
            txn["llm_category"] = _heuristic_category(txn["merchant"])
            txn["category"] = txn["llm_category"]
            txn["llm_failed"] = True
            txn["llm_raw_response"] = raw_response
        return transactions, raw_response, True


def generate_narrative_summary(
    transactions: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None, bool]:
    total_inr = sum(t["amount"] for t in transactions if t["currency"] == "INR")
    total_usd = sum(t["amount"] for t in transactions if t["currency"] == "USD")
    anomaly_count = sum(1 for t in transactions if t.get("is_anomaly"))

    merchant_totals: dict[str, float] = {}
    for txn in transactions:
        merchant_totals[txn["merchant"]] = (
            merchant_totals.get(txn["merchant"], 0) + txn["amount"]
        )
    top_merchants = sorted(
        [{"merchant": m, "total": round(v, 2)} for m, v in merchant_totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )[:3]

    prompt = f"""Analyze these transaction statistics and return ONLY valid JSON:
{{
  "total_spend_inr": {round(total_inr, 2)},
  "total_spend_usd": {round(total_usd, 2)},
  "top_merchants": {json.dumps(top_merchants)},
  "anomaly_count": {anomaly_count},
  "narrative": "2-3 sentence spending summary",
  "risk_level": "low|medium|high"
}}

Base risk_level on anomaly_count and spending patterns. anomaly_count is {anomaly_count}.
"""

    raw_response, failed = _call_with_retry(prompt)
    fallback = {
        "total_spend_inr": round(total_inr, 2),
        "total_spend_usd": round(total_usd, 2),
        "top_merchants": top_merchants,
        "anomaly_count": anomaly_count,
        "narrative": (
            f"Processed {len(transactions)} transactions with "
            f"{anomaly_count} anomalies flagged. "
            f"Total spend: INR {total_inr:,.2f} and USD {total_usd:,.2f}."
        ),
        "risk_level": "high" if anomaly_count >= 5 else "medium" if anomaly_count >= 2 else "low",
    }

    if failed or not raw_response:
        return fallback, None, True

    try:
        parsed = json.loads(raw_response)
        for key in fallback:
            if key not in parsed:
                parsed[key] = fallback[key]
        if parsed.get("risk_level") not in {"low", "medium", "high"}:
            parsed["risk_level"] = fallback["risk_level"]
        return parsed, raw_response, False
    except json.JSONDecodeError:
        return fallback, raw_response, True


def build_category_breakdown(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    breakdown: dict[str, dict[str, Any]] = {}
    for txn in transactions:
        cat = txn["category"]
        if cat not in breakdown:
            breakdown[cat] = {
                "category": cat,
                "total_inr": 0.0,
                "total_usd": 0.0,
                "transaction_count": 0,
            }
        entry = breakdown[cat]
        entry["transaction_count"] += 1
        if txn["currency"] == "INR":
            entry["total_inr"] += txn["amount"]
        else:
            entry["total_usd"] += txn["amount"]

    for entry in breakdown.values():
        entry["total_inr"] = round(entry["total_inr"], 2)
        entry["total_usd"] = round(entry["total_usd"], 2)

    return sorted(breakdown.values(), key=lambda x: x["category"])
