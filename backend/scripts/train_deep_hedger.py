from __future__ import annotations

import argparse
from pathlib import Path

from app.services.deep_hedger import MODEL_PATH, evaluate_policy_cvar, train_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the deep hedging policy")
    parser.add_argument("--scenarios", type=int, default=50_000)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=MODEL_PATH)
    args = parser.parse_args()

    policy = train_policy(
        n_scenarios=args.scenarios,
        epochs=args.epochs,
        batch_size=args.batch_size,
        seed=args.seed,
        output_path=args.output,
    )
    policy_cvar = evaluate_policy_cvar(policy, seed=args.seed + 1)
    random_cvar = evaluate_policy_cvar(policy, seed=args.seed + 1, random_hedge=True)
    print(f"saved={args.output} policy_cvar={policy_cvar:.2f} random_cvar={random_cvar:.2f}")


if __name__ == "__main__":
    main()
