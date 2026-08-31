.PHONY: all

CASE ?=
SEED ?=

all:
	@test -n "$(CASE)" || (echo "CASE is required" >&2; exit 2)
	@test -n "$(SEED)" || (echo "SEED is required" >&2; exit 2)
	python3 -u scripts/simulate.py --case "$(CASE)" --seed "$(SEED)" \
		--compile-log "artifacts/$(CASE).compile.log" \
		--run-log "artifacts/$(CASE).run.log"
