SHELL := /bin/sh

UV ?= uv
PYTHON ?= python3
REDUP ?= redup
REPORT_DIR ?= .ci-reports
API_URL ?= http://127.0.0.1:18788

.PHONY: help setup test duplicates check build report report-full status \
	up up-local down logs health docker-build

help:
	@echo "doDSL developer commands"
	@echo "  make setup         sync every workspace package"
	@echo "  make test          run the local test suite"
	@echo "  make duplicates    reject meaningful Python duplication"
	@echo "  make check         run tests and the duplication gate"
	@echo "  make build         build all five distributions"
	@echo "  make report        write PASS/FAIL/SKIP report to $(REPORT_DIR)"
	@echo "  make report-full   also test configured external adapters and Docker"
	@echo "  make up|down|logs  control the pinned development service"
	@echo "  make up-local ONLYDSL_REPO=<path>  mount an onlyDSL source checkout"
	@echo "  make health        check $(API_URL)/health"

setup:
	@$(UV) sync --all-packages

test:
	@$(UV) run --all-packages pytest -q

duplicates:
	@command -v "$(REDUP)" >/dev/null 2>&1 || { echo "NOT RUN duplicates: install redup"; exit 2; }
	@$(REDUP) check packages --ext .py --min-lines 8 --max-groups 0 --max-lines 0

check: test duplicates

build:
	@$(UV) build --all-packages --out-dir dist

report:
	@$(PYTHON) scripts/status_report.py --root . --output-dir "$(REPORT_DIR)"

report-full:
	@$(PYTHON) scripts/status_report.py --root . --output-dir "$(REPORT_DIR)" --external --docker

status:
	@test -f "$(REPORT_DIR)/status.md" || { echo "status report absent; run: make report"; exit 2; }
	@cat "$(REPORT_DIR)/status.md"

docker-build:
	@docker compose build

up:
	@docker compose up -d --build

up-local:
	@test -n "$(ONLYDSL_REPO)" || { echo "ONLYDSL_REPO is required"; exit 2; }
	@ONLYDSL_REPO="$(ONLYDSL_REPO)" docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

down:
	@docker compose down

logs:
	@docker compose logs -f --tail=100

health:
	@curl --fail --silent --show-error "$(API_URL)/health"
	@echo
