.PHONY: dev test seed docker-up docker-down lint clean

# ============================================================
# Local Development
# ============================================================

dev:
	cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000

seed:
	cd backend && ./venv/bin/python -m app.scripts.seed_demo

test:
	cd backend && ./venv/bin/python -m pytest tests/ -v --tb=short

test-cov:
	cd backend && ./venv/bin/python -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

# ============================================================
# Docker
# ============================================================

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-test:
	docker-compose exec backend python -m pytest tests/ -v --tb=short

# ============================================================
# Utility
# ============================================================

lint:
	cd backend && ./venv/bin/python -m ruff check app/ tests/

clean:
	rm -f backend/dev.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
