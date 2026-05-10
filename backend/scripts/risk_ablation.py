from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.db.base import Base
from app.db.session import engine
from app.services.risk_ablation import run_risk_ablation


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-coefficient risk ablation")
    parser.add_argument("--market", required=True, help="Market code, e.g. GB_POWER")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--position-gbp", type=float, default=10_000.0)
    parser.add_argument("--direction", choices=["long", "short"], default="long")
    parser.add_argument("--horizon-hours", type=int, default=1)
    parser.add_argument("--n-paths", type=int, default=1000)
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    result = run_risk_ablation(
        args.market,
        args.lookback_days,
        args.position_gbp,
        direction=args.direction,
        horizon_hours=args.horizon_hours,
        n_paths=args.n_paths,
        max_samples=args.max_samples,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out_path = REPORTS_DIR / f"ablation_{args.market}_{stamp}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(
        f"{args.market}: with_llm={result['breach_rate_with_llm']:.3f} "
        f"without_llm={result['breach_rate_without_llm']:.3f} "
        f"n={result['sample_count']} -> {out_path.name}"
    )


if __name__ == "__main__":
    main()
