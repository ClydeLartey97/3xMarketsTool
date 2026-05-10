from __future__ import annotations

import json

from scripts.finetune_news_scorer import (
    build_sft_rows,
    format_sft_example,
    load_jsonl_records,
    write_training_manifest,
)


def test_finetune_script_formats_label_json(tmp_path) -> None:
    record = {
        "id": "row-1",
        "text": "ERCOT generator outage removes 900 MW from North Hub.",
        "label_dict": {
            "event_type": "generator_outage",
            "price_direction": "bullish",
            "label_confidence": 0.86,
        },
        "metadata": {"source_family": "unit_test"},
    }

    formatted = format_sft_example(record)

    assert "NEWS ARTICLE:" in formatted
    assert '"event_type":"generator_outage"' in formatted
    assert formatted.endswith("</s>")

    rows = build_sft_rows([record])
    assert rows == [{"text": formatted}]

    manifest_path = write_training_manifest(
        tmp_path,
        dataset_path=tmp_path / "news_train.jsonl",
        base_model="unit/model",
        rows=[record],
        dry_run=True,
        max_seq_length=512,
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["dry_run"] is True
    assert manifest["event_counts"] == {"generator_outage": 1}


def test_load_jsonl_records_validates_shape(tmp_path) -> None:
    path = tmp_path / "sample.jsonl"
    path.write_text(
        json.dumps({"text": "article", "label_dict": {"event_type": "demand_shock"}}) + "\n",
        encoding="utf-8",
    )

    records = load_jsonl_records(path)

    assert records[0]["label_dict"]["event_type"] == "demand_shock"
