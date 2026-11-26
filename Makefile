# Atalhos: tudo roda dentro do Docker.
.PHONY: up down logs test migrate revision seed sim url psql validar avaliar

up:
	docker compose up -d --build db api voice-agent tunnel

down:
	docker compose down

logs:
	docker compose logs -f api voice-agent tunnel

test:
	docker compose run --rm --build test pytest -q $(ARGS)

migrate:
	docker compose run --rm api alembic upgrade head

revision:
	docker compose run --rm api alembic revision --autogenerate -m "$(MSG)"

seed:
	docker compose run --rm api python -m app.seed $(ARGS)

sim:
	docker compose exec api python /scripts/simular_rota.py --api http://localhost:8000 $(ARGS)

url:
	@docker compose exec api python -c "from app.integracoes.tunel import url_publica; print(url_publica())"

psql:
	docker compose exec db psql -U avisai avisai

# Validação ponta a ponta contra a api real (relatório em evidence/validacao.md; progresso no terminal)
validar:
	mkdir -p evidence
	docker compose exec -T api python /scripts/validar_fluxos.py > evidence/validacao.md

# Conversas difíceis contra o LLM de verdade (reinicia a rota usada; padrão: rota 1)
avaliar:
	docker compose exec -T api python /scripts/avaliar_conversas.py $(ARGS)
