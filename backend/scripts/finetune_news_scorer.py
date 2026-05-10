"""LoRA fine-tune entrypoint for the domain news scorer.

The heavy training dependencies are imported only inside `run_training` so the
data formatting helpers remain testable in the normal backend environment.

Usage:
    PYTHONPATH=. python3 scripts/finetune_news_scorer.py --dry-run
    PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id meta-llama/Llama-3.1-8B-Instruct
    PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id Qwen/Qwen2.5-7B-Instruct
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data" / "news_train.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "models" / "news_scorer_lora"
DEFAULT_MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

SYSTEM_PROMPT = (
    "You are a power-market news scorer. Return only compact JSON matching the "
    "provided label schema. Identify event type, affected region, direction, "
    "severity, catalyst severity, asymmetry, tail multiplier, regime, and confidence."
)


def load_jsonl_records(path: Path, *, max_rows: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if max_rows is not None and len(records) >= max_rows:
                break
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record.get("text"), str) or not isinstance(record.get("label_dict"), dict):
                raise ValueError(f"invalid training row shape at row {len(records) + 1}")
            records.append(record)
    if not records:
        raise ValueError(f"no training records loaded from {path}")
    return records


def format_sft_example(record: dict[str, Any]) -> str:
    label_json = json.dumps(record["label_dict"], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    user = f"NEWS ARTICLE:\n{record['text'].strip()}\n\nReturn the label JSON."
    return (
        "<s>[INST] <<SYS>>\n"
        f"{SYSTEM_PROMPT}\n"
        "<</SYS>>\n\n"
        f"{user} [/INST]\n"
        f"{label_json}</s>"
    )


def build_sft_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"text": format_sft_example(record)} for record in records]


def write_training_manifest(
    output_dir: Path,
    *,
    dataset_path: Path,
    base_model: str,
    rows: list[dict[str, Any]],
    dry_run: bool,
    max_seq_length: int,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for record in rows:
        event_type = str(record["label_dict"].get("event_type", "unknown"))
        source_family = str((record.get("metadata") or {}).get("source_family", "unknown"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        source_counts[source_family] = source_counts.get(source_family, 0) + 1
    manifest = {
        "base_model": base_model,
        "dataset_path": str(dataset_path),
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_seq_length": max_seq_length,
        "row_count": len(rows),
        "event_counts": event_counts,
        "source_counts": source_counts,
        "sample_ids": [str(record.get("id")) for record in rows[:5]],
        "output_contract": {
            "adapter_config": "adapter_config.json",
            "adapter_weights": "adapter_model.safetensors",
            "tokenizer": "tokenizer files saved by transformers",
        },
    }
    path = output_dir / "training_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_training(args: argparse.Namespace) -> None:
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise SystemExit(
            "Training dependencies are missing. Install with: "
            "python -m pip install -r backend/requirements-train.txt"
        ) from exc

    records = load_jsonl_records(args.dataset, max_rows=args.max_rows)
    sft_rows = build_sft_rows(records)
    dataset = Dataset.from_list(sft_rows)

    tokenizer = AutoTokenizer.from_pretrained(args.model_id, use_fast=True, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    cuda_available = bool(torch.cuda.is_available())
    if not cuda_available:
        print("warning: CUDA is not available; this 7B/8B LoRA run is expected to be slow or memory-bound.")
    dtype = torch.bfloat16 if cuda_available else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        device_map="auto" if cuda_available else None,
        torch_dtype=dtype,
        trust_remote_code=True,
    )

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    training_args = SFTConfig(
        output_dir=str(args.output_dir),
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_strategy="epoch",
        bf16=cuda_available,
        fp16=False,
        report_to=[],
    )
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        peft_config=lora_config,
        tokenizer=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    write_training_manifest(
        args.output_dir,
        dataset_path=args.dataset,
        base_model=args.model_id,
        rows=records,
        dry_run=False,
        max_seq_length=args.max_seq_length,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune the domain news scorer with LoRA")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-seq-length", type=int, default=1536)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_jsonl_records(args.dataset, max_rows=args.max_rows)
    if args.dry_run:
        rows = build_sft_rows(records)
        manifest_path = write_training_manifest(
            args.output_dir,
            dataset_path=args.dataset,
            base_model=args.model_id,
            rows=records,
            dry_run=True,
            max_seq_length=args.max_seq_length,
        )
        print(
            json.dumps(
                {
                    "dataset": str(args.dataset),
                    "dry_run": True,
                    "formatted_rows": len(rows),
                    "manifest": str(manifest_path),
                    "sample_chars": len(rows[0]["text"]),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_training(args)


if __name__ == "__main__":
    main()
