# Developer targets.  `make help` lists them.
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BIN := $(dir $(PY))
.DEFAULT_GOAL := help
.PHONY: help test lint check data app fixtures

help:  ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-9s %s\n", $$1, $$2}'

test:  ## offline pytest suite
	$(PY) -m pytest

lint:  ## ruff
	$(BIN)ruff check .

check: lint test  ## lint, then test

data:  ## fetch fresh public data and score it into data/scored/
	$(BIN)open-bps fetch all && $(BIN)open-bps score all

app:  ## run the lookup app
	$(BIN)streamlit run app/streamlit_app.py

fixtures:  ## regenerate test fixtures from the latest snapshot in data/
	$(PY) scripts/make_fixtures.py --root data
