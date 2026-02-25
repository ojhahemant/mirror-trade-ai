.PHONY: setup dev prod train backtest test clean logs shell-api shell-db

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

# ── Setup ─────────────────────────────────────────────────────────────────────
setup:
	@echo "$(GREEN)Setting up Mirror Trade AI...$(NC)"
	@cp -n .env.example .env 2>/dev/null || true
	@echo "$(YELLOW)⚠  Edit .env with your API keys before continuing$(NC)"
	@docker compose build
	@docker compose up -d postgres redis
	@sleep 5
	@docker compose run --rm api python -c "from api.database import init_db; import asyncio; asyncio.run(init_db())"
	@echo "$(GREEN)✓ Setup complete! Run 'make dev' to start$(NC)"

# ── Development ───────────────────────────────────────────────────────────────
dev:
	@echo "$(GREEN)Starting development stack...$(NC)"
	@docker compose up -d
	@echo "$(GREEN)✓ Services started:$(NC)"
	@echo "  API:      http://localhost:8000/docs"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Nginx:    http://localhost:80"

# ── Production ────────────────────────────────────────────────────────────────
prod:
	@echo "$(GREEN)Starting production stack...$(NC)"
	@docker compose -f docker-compose.yml up -d --build
	@echo "$(GREEN)✓ Production stack running$(NC)"

# ── ML Training ───────────────────────────────────────────────────────────────
train:
	@echo "$(GREEN)Starting model training pipeline...$(NC)"
	@docker compose run --rm api python -m ml.model_engine --action train
	@echo "$(GREEN)✓ Model training complete$(NC)"

# ── Backtest ──────────────────────────────────────────────────────────────────
backtest:
	@echo "$(GREEN)Running full historical backtest...$(NC)"
	@docker compose run --rm api python -m ml.backtester --from 2022-01-01 --to 2024-12-31
	@echo "$(GREEN)✓ Backtest complete. Check reports/$(NC)"

# ── Data Backfill ─────────────────────────────────────────────────────────────
backfill:
	@echo "$(GREEN)Backfilling 3 years of historical data...$(NC)"
	@docker compose run --rm api python -m data.data_pipeline --action backfill
	@echo "$(GREEN)✓ Backfill complete$(NC)"

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	@echo "$(GREEN)Running test suite...$(NC)"
	@docker compose run --rm api pytest tests/ -v --tb=short
	@echo "$(GREEN)✓ Tests complete$(NC)"

# ── Logs ──────────────────────────────────────────────────────────────────────
logs:
	@docker compose logs -f --tail=100

logs-api:
	@docker compose logs -f api --tail=100

logs-celery:
	@docker compose logs -f celery-worker celery-beat --tail=100

# ── Shells ────────────────────────────────────────────────────────────────────
shell-api:
	@docker compose exec api bash

shell-db:
	@docker compose exec postgres psql -U $${POSTGRES_USER:-mirrortrade} -d $${POSTGRES_DB:-mirrortrade_db}

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	@echo "$(RED)Stopping and removing all containers...$(NC)"
	@docker compose down -v
	@echo "$(GREEN)✓ Cleaned up$(NC)"

stop:
	@docker compose down

restart:
	@docker compose restart

# ── Frontend helpers ──────────────────────────────────────────────────────────
frontend-install:
	@cd frontend && npm install

frontend-dev:
	@cd frontend && npm run dev

frontend-build:
	@cd frontend && npm run build
