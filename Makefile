# Atalhos: tudo roda dentro do Docker.
.PHONY: up down logs test migrate revision seed sim url psql twilio

up:
	docker compose up -d --build db api tunnel

down:
	docker compose down

logs:
	docker compose logs -f api tunnel

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

# Configura o Elastic SIP Trunk da Twilio (lê TWILIO_* do .env; não imprime segredos)
twilio:
	docker compose run --rm -T api python /scripts/twilio_trunk.py
