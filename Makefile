.PHONY: help install up down db reset verify test lint worker reaper clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## install the package and dev deps (editable)
	pip install -e ".[dev]"

up:  ## start postgres (+minio) and wait for health
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U dev -d explainer >/dev/null 2>&1; do sleep 1; done
	@echo "postgres ready"

down:  ## stop containers
	docker compose down

db:  ## apply migrations
	explainer db init

reset:  ## drop and recreate the schema (destructive)
	explainer db reset --yes

verify:  ## Phase 1 exit criteria — the regression gate for the invalidation model
	explainer verify

test:  ## unit + integration tests
	python -m pytest -q

lint:
	ruff check src tests

worker:  ## run a worker over all pools
	explainer run

reaper:  ## requeue jobs from dead workers, every 30s
	while true; do explainer reap; sleep 30; done

clean:  ## remove the local artifact store (cache only — safe, everything rebuilds)
	rm -rf .artifacts
