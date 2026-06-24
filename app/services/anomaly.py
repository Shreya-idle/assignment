from collections import defaultdict
from statistics import median
from typing import Any

DOMESTIC_ONLY_MERCHANTS = {"swiggy", "ola", "irctc"}


def detect_anomalies(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, list[float]] = defaultdict(list)
    for txn in transactions:
        by_account[txn["account_id"]].append(txn["amount"])

    account_medians = {
        account: median(amounts) for account, amounts in by_account.items()
    }

    for txn in transactions:
        reasons: list[str] = []
        acct_median = account_medians.get(txn["account_id"], 0)
        if acct_median > 0 and txn["amount"] > 3 * acct_median:
            reasons.append(
                f"Amount {txn['amount']:.2f} exceeds 3x account median ({acct_median:.2f})"
            )

        merchant_lower = txn["merchant"].lower()
        if txn["currency"] == "USD" and merchant_lower in DOMESTIC_ONLY_MERCHANTS:
            reasons.append(
                f"USD transaction at domestic-only merchant {txn['merchant']}"
            )

        txn["is_anomaly"] = bool(reasons)
        txn["anomaly_reason"] = "; ".join(reasons) if reasons else None

    return transactions
