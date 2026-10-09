import json
import os
from collections import Counter

LEDGER_FILE = os.getenv(
    "PF_BRAIN_LEDGER",
    "data/purple_falcon_brain_ledger.jsonl"
)

def metrics():

    actions = Counter()
    intents = Counter()

    total = 0

    try:

        with open(
            LEDGER_FILE,
            encoding="utf-8"
        ) as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                row = json.loads(line)

                total += 1

                actions[
                    row.get("action")
                ] += 1

                intents[
                    row.get("intent")
                ] += 1

    except Exception:

        return {
            "total": 0,
            "actions": {},
            "intents": {}
        }

    return {
        "total": total,
        "actions": dict(actions),
        "intents": dict(intents)
    }
