# News Scorer LoRA Output

This directory is the output target for D.2:

```bash
cd backend
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --dry-run
PYTHONPATH=. python3 scripts/finetune_news_scorer.py --model-id meta-llama/Llama-3.1-8B-Instruct
```

The committed `training_manifest.json` is produced by a dry run so downstream
code has a stable output contract before GPU training is executed. A real LoRA
run will add `adapter_config.json`, `adapter_model.safetensors`, and tokenizer
files in this directory.
