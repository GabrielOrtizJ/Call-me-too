 .PHONY: install run debug clean lint lint-strict help

help:
	@echo "Available targets:"
	@echo "  install      - Install project dependencies"
	@echo "  run          - Execute the main script"
	@echo "  debug        - Run the main script in debug mode"
	@echo "  clean        - Remove temporary files and caches"
	@echo "  lint         - Run flake8 and mypy checks"
	@echo "  lint-strict  - Run strict mypy checks"

install:
	python3 -m pip install -r requirements.txt

run:
	python3 main.py map.txt

debug:
	python3 -m pdb main.py map.txt

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

lint:
	python3 -m flake8 .
	python3 -m mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	python3 -m flake8 .
	python3 -m mypy . --strict
