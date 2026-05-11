from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.news_scorer_validation import (
    DEFAULT_GOLDEN_PATH,
    adapter_weights_present,
    compare_predictors,
    domain_lora_predict,
    load_golden_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate domain news scorer against golden set")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--min-improvement-pp", type=float, default=15.0)
    args = parser.parse_args()

    if not adapter_weights_present():
        raise SystemExit("Domain LoRA adapter weights are missing; D.6 remains blocked.")

    result = compare_predictors(
        load_golden_records(args.golden),
        domain_predictor=domain_lora_predict,
        min_improvement_pp=args.min_improvement_pp,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
