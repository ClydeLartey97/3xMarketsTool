from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.events.extractor import extract_primary_event
from app.services.llm_scorer import ScoredArticle, _parse_json_loose, _score_heuristic


DEFAULT_GOLDEN_PATH = Path(__file__).resolve().parents[2] / "tests" / "data" / "news_golden.jsonl"
LABEL_KEYS = ("event_type", "price_direction", "severity", "regime")


@dataclass(frozen=True)
class GoldenRecord:
    text: str
    label_dict: dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    sample_count: int
    heuristic_accuracy: float
    domain_accuracy: float
    improvement_pp: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "heuristic_accuracy": round(self.heuristic_accuracy, 4),
            "domain_accuracy": round(self.domain_accuracy, 4),
            "improvement_pp": round(self.improvement_pp, 2),
            "passed": self.passed,
        }


Predictor = Callable[[GoldenRecord], dict[str, Any]]


def load_golden_records(path: Path = DEFAULT_GOLDEN_PATH) -> list[GoldenRecord]:
    records: list[GoldenRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload.get("text"), str) or not isinstance(payload.get("label_dict"), dict):
                raise ValueError(f"invalid golden row at line {line_number}")
            records.append(GoldenRecord(text=payload["text"], label_dict=payload["label_dict"]))
    return records


def heuristic_predict(record: GoldenRecord) -> dict[str, Any]:
    title, body = _split_title_body(record.text)
    event = extract_primary_event(title, body, str(record.label_dict.get("affected_region", "ERCOT")))
    events_summary = []
    if event:
        events_summary.append(
            {
                "event_type": event.event_type,
                "severity": event.severity,
                "affected_region": event.affected_region,
                "title": event.title,
            }
        )
    score = _score_heuristic(
        [
            ScoredArticle(
                title=title,
                summary=body,
                source="golden",
                published_at=datetime.now(timezone.utc),
                credibility=90.0,
            )
        ],
        events_summary,
    )
    return {
        "event_type": event.event_type if event else "no_event",
        "price_direction": event.price_direction if event else "neutral",
        "severity": event.severity if event else "low",
        "regime": score["regime"],
    }


def domain_lora_predict(record: GoldenRecord) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.services.llm_scorer import _load_domain_runtime

    tokenizer, model = _load_domain_runtime(get_settings())
    prompt = _domain_validation_prompt(record.text)
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1536)
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("torch is required for domain scorer validation") from exc
    device = next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated_ids = output[0][inputs["input_ids"].shape[-1]:]
    parsed = _parse_json_loose(tokenizer.decode(generated_ids, skip_special_tokens=True))
    return _normalize_prediction(parsed)


def compare_predictors(
    records: list[GoldenRecord],
    *,
    domain_predictor: Predictor,
    heuristic_predictor: Predictor = heuristic_predict,
    min_improvement_pp: float = 15.0,
) -> ValidationResult:
    if not records:
        raise ValueError("golden validation requires at least one record")
    heuristic_accuracy = _accuracy(records, heuristic_predictor)
    domain_accuracy = _accuracy(records, domain_predictor)
    improvement_pp = (domain_accuracy - heuristic_accuracy) * 100.0
    return ValidationResult(
        sample_count=len(records),
        heuristic_accuracy=heuristic_accuracy,
        domain_accuracy=domain_accuracy,
        improvement_pp=improvement_pp,
        passed=improvement_pp >= min_improvement_pp,
    )


def adapter_weights_present(model_dir: Path | None = None) -> bool:
    if model_dir is None:
        from app.core.config import get_settings

        configured = Path(get_settings().domain_scorer_model_dir)
        model_dir = configured if configured.is_absolute() else Path(__file__).resolve().parents[2] / configured
    return (model_dir / "adapter_config.json").exists() and (model_dir / "adapter_model.safetensors").exists()


def _accuracy(records: list[GoldenRecord], predictor: Predictor) -> float:
    correct = 0
    total = 0
    for record in records:
        prediction = _normalize_prediction(predictor(record))
        expected = _normalize_prediction(record.label_dict)
        for key in LABEL_KEYS:
            total += 1
            if prediction.get(key) == expected.get(key):
                correct += 1
    return correct / max(total, 1)


def _normalize_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: str(payload.get(key, "")).strip().lower() for key in LABEL_KEYS}


def _split_title_body(text: str) -> tuple[str, str]:
    parts = text.strip().split("\n\n", 1)
    if len(parts) == 1:
        return parts[0][:256], parts[0]
    return parts[0][:256], parts[1]


def _domain_validation_prompt(text: str) -> str:
    return (
        "<s>[INST] <<SYS>>\n"
        "You are a power-market event classifier. Return only JSON with keys "
        "event_type, price_direction, severity, and regime.\n"
        "<</SYS>>\n\n"
        f"NEWS ARTICLE:\n{text.strip()}\n\n"
        "Return the label JSON. [/INST]\n"
    )
