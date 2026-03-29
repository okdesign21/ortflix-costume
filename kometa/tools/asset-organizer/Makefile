.PHONY: help run test test-watch lint format clean install setup check

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/activate: pyproject.toml
	@echo "Creating virtual environment..."
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip --quiet
	@$(PIP) install -e ".[test,dev]" --quiet
	@touch $(VENV)/bin/activate

install: $(VENV)/bin/activate ## Install dependencies in virtual environment
	@echo "✅ Dependencies installed"

run: install ## Run the asset organizer script
	@echo "Running asset organizer..."
	@$(PYTHON) organize_assets.py

test: install ## Run tests
	@echo "Running tests..."
	@$(PYTEST)

test-watch: install ## Run tests in watch mode
	@echo "Running tests in watch mode..."
	@$(PYTEST) --looponfail

lint: install ## Run linting
	@echo "Running linting..."
	@$(RUFF) check .

format: install ## Format code
	@echo "Formatting code..."
	@$(RUFF) check --fix .

clean: ## Clean up generated files and caches
	@echo "Cleaning up..."
	@rm -rf .venv .pytest_cache .ruff_cache htmlcov .coverage _version.py *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup complete"

check: lint test ## Run all checks (lint + test)
