.PHONY: run stop setup dev check

run:
	@bash scripts/run_it.sh

stop:
	@bash scripts/stop_local.sh

setup:
	@bash scripts/bootstrap_local.sh

dev:
	@bash scripts/run_local.sh

check:
	@bash scripts/check_local.sh
