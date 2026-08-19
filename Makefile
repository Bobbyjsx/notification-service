.PHONY: install run lint lint-fix format test clean

VENV = .venv/bin

install:
	$(VENV)/pip install -r requirements.txt -r requirements-dev.txt

run:
	docker compose up --build --watch notification-service
	docker image prune -f

lint:
	$(VENV)/ruff check .

lint-fix:
	$(VENV)/ruff check . --fix

format:
	$(VENV)/ruff format .

test:
	PYTHONPATH=. $(VENV)/pytest tests/

clean:
	rm -rf __pycache__ .ruff_cache .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	docker compose down --rmi local
	docker image prune -f
