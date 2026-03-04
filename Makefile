.PHONY: help install test lint format demo backup clean

help:
	@echo "Scope Tracker — Development Commands"
	@echo ""
	@echo "  make install       Install optional dependencies (pytest, black, etc)"
	@echo "  make demo          Run 8-week engagement simulation"
	@echo "  make test          Run test suite (requires pytest)"
	@echo "  make lint          Run code quality checks (flake8, mypy)"
	@echo "  make format        Auto-format code (black)"
	@echo "  make backup        Create timestamped backup of all data"
	@echo "  make clean         Remove __pycache__ and .pyc files"
	@echo ""

install:
	pip install -r requirements.txt

demo:
	python -m demo.simulate_engagement

test:
	pytest tests/ -v --cov=src --cov=importers --cov=storage --cov=export

lint:
	flake8 src/ importers/ storage/ export/ demo/ --max-line-length=100
	mypy src/ importers/ storage/ export/ demo/ --ignore-missing-imports

format:
	black src/ importers/ storage/ export/ demo/ docs/

backup:
	@python -c "from storage.json_store import JSONStore; import time; \
	store = JSONStore(); \
	backup_file = f'backups/scope-tracker-{int(time.time())}.zip'; \
	store.backup(backup_file); \
	echo 'Backup created: {backup_file}'"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".DS_Store" -delete

# Development/Testing targets

# Run importer test
test-importer:
	python -m importers.time_entry_importer

# Run drift detector test
test-detector:
	python -m src.drift_detector

# Run change order generator test
test-generator:
	python -m src.change_order_generator

# Run JSON store test
test-store:
	python -m storage.json_store

# Run engagement tracker test
test-engagement:
	python -m src.engagement_tracker
