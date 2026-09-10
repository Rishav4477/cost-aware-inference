.PHONY: install test lint demo smoke compose down
install:
	python -m pip install -r requirements-dev.lock
test:
	python -m pytest -q
lint:
	ruff check .
	ruff format --check .
demo:
	python scripts/run_demo.py
smoke:
	python scripts/smoke.py
compose:
	docker compose up --build -d
down:
	docker compose down
