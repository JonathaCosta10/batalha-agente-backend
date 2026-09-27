# Imagem do backend-agente-conversacional para o Cloud Run (serviço NOVO proposto: i-agora-conversacional).
# Criado em 2026-09-27. NÃO construída nem publicada: o deploy é a etapa final, depois do OK do Henrique.
# Comando e variáveis: docs/decisoes-e-logica-2026-09-27.md §5.4.
#
# Segredos NUNCA entram na imagem (.dockerignore exclui .secrets e .env*). Em produção:
#   DJANGO_SECRET_KEY  <- Secret Manager (obrigatória com DJANGO_DEBUG=0; sem ela o app não sobe)
#   API_KEY_SECRECT    <- Secret Manager (chave do Gemini; lida por desafio_itau/segredos.py)
# Sem collectstatic: o projeto não tem estático próprio (não há pasta static/) e as rotas usadas pelo front são JSON.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DJANGO_DEBUG=0 \
    SQLITE_PATH=/tmp/db.sqlite3

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Usuário sem privilégio. relatorios/ recebe o ledger de avaliações (disco efêmero no Cloud Run).
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /app/relatorios \
    && chown -R app /app/relatorios \
    && chmod -R a+rX /app
USER 10001

# init_database.py roda o migrate e popula o SQLite em /tmp (idempotente); depois o gunicorn escuta em $PORT.
CMD ["sh", "-c", "python init_database.py && exec gunicorn desafio_itau.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]
