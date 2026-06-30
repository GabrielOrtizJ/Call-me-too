UV				= ~/.local/bin/uv
V_PYTHON		= $(UV) run python
V_PIP			= $(UV) pip
MAIN			= src/__main__.py
VENV			= .venv

MYPY_FLAGS		= --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs
DEPENDENCIES	= pytest flake8 mypy
FLAKE			= $(V_PYTHON) -m flake8
MYPY			= $(V_PYTHON) -m mypy

 .PHONY: install run debug clean lint lint-strict help

help:
	@echo "Available targets:"
	@echo "  install      - Install project dependencies"
	@echo "  run          - Execute the main script"
	@echo "  debug        - Run the main script in debug mode"
	@echo "  clean        - Remove temporary files and caches"
	@echo "  lint         - Run flake8 and mypy checks"
	@echo "  lint-strict  - Run strict mypy checks"

all: run

$(VENV):
	$(UV) venv

run: install
	$(V_PYTHON) -m src

install: $(VENV)
	$(V_PIP) install torch --index-url https://download.pytorch.org/whl/cpu
	$(V_PIP) install $(DEPENDENCIES)


debug: install
	$(V_PYTHON) -m pdb $(MAIN)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache
	rm -rf $(VENV)
	rm -rf uv.lock
	rm -rf data/output/

lint: install
	$(FLAKE) . --exclude '$(VENV)'
	$(MYPY) $(MYPY_FLAGS) src

lint-strict: install
	$(FLAKE) . --exclude '$(VENV)'
	$(MYPY) $(MYPY_FLAGS) --strict src
 