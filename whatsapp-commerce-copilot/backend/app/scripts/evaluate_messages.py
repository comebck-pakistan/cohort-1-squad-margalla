"""Evaluate anonymized JSONL conversations against a running backend.

Usage:
  python -m app.scripts.evaluate_messages evaluation/messages.jsonl \
    --base-url http://localhost:8000

Keep turns for a conversation in file order. Use a dedicated test database:
the endpoint persists conversation state just like production.
"""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return cases


async def evaluate(cases: list[dict], base_url: str, token: str) -> dict:
    counts = Counter()
    failures = []
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        for index, case in enumerate(cases, 1):
            response = await client.post(
                "/internal/whatsapp/messages",
                headers={"X-Internal-Token": token},
                json={
                    "store_id": case["store_id"],
                    "customer_number": case["customer_number"],
                    "message": case["message"],
                    "whatsapp_message_id": f"evaluation-{case.get('conversation_id', 'case')}-{index}",
                },
            )
            response.raise_for_status()
            actual = response.json()
            counts["turns"] += 1

            expected_action = case.get("expected_action")
            if expected_action is not None:
                counts["action_labeled"] += 1
                if actual["intent"] == expected_action:
                    counts["action_correct"] += 1
                else:
                    failures.append({
                        "turn": index, "field": "action",
                        "expected": expected_action, "actual": actual["intent"],
                    })

            expected_product = case.get("expected_product_id")
            if expected_product is not None:
                counts["product_labeled"] += 1
                if actual.get("matched_product_id") == expected_product:
                    counts["product_top1_correct"] += 1
                else:
                    failures.append({
                        "turn": index, "field": "product",
                        "expected": expected_product,
                        "actual": actual.get("matched_product_id"),
                    })

            for field, expected in case.get("expected_entities", {}).items():
                counts["entity_labeled"] += 1
                value = actual.get("extracted_entities", {}).get(field)
                if value == expected:
                    counts["entity_correct"] += 1
                else:
                    failures.append({
                        "turn": index, "field": f"entity.{field}",
                        "expected": expected, "actual": value,
                    })

            disposition = case.get("expected_disposition")
            actual_disposition = (
                "handoff" if actual.get("needs_human")
                else "clarify" if actual.get("needs_clarification")
                else "answer"
            )
            if disposition:
                counts["disposition_labeled"] += 1
                if disposition == actual_disposition:
                    counts["disposition_correct"] += 1

            # A price/stock response without an inventory source is a grounding
            # violation worth investigating.
            mentions_catalog_fact = (
                "rs." in actual["message"].lower()
                or "stock" in actual["message"].lower()
            )
            has_inventory_source = any(
                source.startswith("inventory:variant:")
                for source in actual.get("sources", [])
            )
            if mentions_catalog_fact and not has_inventory_source:
                counts["grounding_violations"] += 1

    def rate(correct, labeled):
        return round(counts[correct] / counts[labeled], 4) if counts[labeled] else None

    return {
        "turns": counts["turns"],
        "action_accuracy": rate("action_correct", "action_labeled"),
        "product_top1_accuracy": rate("product_top1_correct", "product_labeled"),
        "entity_accuracy": rate("entity_correct", "entity_labeled"),
        "disposition_accuracy": rate("disposition_correct", "disposition_labeled"),
        "grounding_violations": counts["grounding_violations"],
        "failures": failures,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default="dev-internal-token")
    args = parser.parse_args()
    report = await evaluate(load_cases(args.dataset), args.base_url, args.token)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
