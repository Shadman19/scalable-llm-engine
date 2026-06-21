.PHONY: help install run worker test up down logs smoke

help:
	@echo "Targets:"
	@echo "  install  - install python deps locally"
	@echo "  run      - run the API locally (needs local Redis)"
	@echo "  worker   - run a worker locally"
	@echo "  up       - docker compose up (redis + api + worker)"
	@echo "  down     - docker compose down"
	@echo "  logs     - tail compose logs"
	@echo "  test     - run unit tests"
	@echo "  smoke    - hit the running API with a smoke test"

install:
	pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	python -m app.worker

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -q

smoke:
	bash scripts/smoke_test.sh
