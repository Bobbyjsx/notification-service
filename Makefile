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
	docker compose up --build -d firestore
	sleep 5
	PYTHONPATH=. $(VENV)/pytest tests/ || (docker compose down && exit 1)
	docker compose down

clean:
	@echo "Cleaning up python cache files..."
	rm -rf __pycache__ .ruff_cache .pytest_cache
	find . -not -path './.venv*' -type d -name "__pycache__" -exec rm -rf {} +
	docker compose down --rmi local
	docker image prune -f
