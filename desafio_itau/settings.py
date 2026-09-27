"""
Django settings for desafio-itau-batalha-de-agentes-time2 project.
Configuração minimalista sem dependência obrigatória de banco de dados SQL.
Orientada à contextualização de agentes de recomendação e templates pré-definidos.
"""

from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Produção (Cloud Run, 2026-09-27): tudo abaixo vem do ambiente. Sem a variável, vale o comportamento local de antes
# (DEBUG ligado, chave de desenvolvimento, qualquer host). Os nomes DJANGO_* têm prioridade; DEBUG, SECRET_KEY e
# ALLOWED_HOSTS sem prefixo são aceitos como alternativa. Detalhe: docs/decisoes-e-logica-2026-09-27.md §5.


def _env(*nomes, padrao=None):
    for nome in nomes:
        valor = os.environ.get(nome)
        if valor is not None and valor.strip() != '':
            return valor.strip()
    return padrao


def _env_lista(*nomes):
    valor = _env(*nomes)
    return [item.strip() for item in valor.split(',') if item.strip()] if valor else None


DEBUG = _env('DJANGO_DEBUG', 'DEBUG', padrao='1').lower() not in ('0', 'false', 'off', 'nao', 'não', 'no')

# Chave só de desenvolvimento. Com DEBUG=0 ela é recusada: o app falha ao subir se DJANGO_SECRET_KEY faltar.
SECRET_KEY_DESENVOLVIMENTO = 'django-insecure-desafio-itau-batalha-de-agentes-time2-secret-key-2026'
SECRET_KEY = _env('DJANGO_SECRET_KEY', 'SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            'DEBUG=0 exige DJANGO_SECRET_KEY no ambiente (no Cloud Run, montada do Secret Manager). '
            'A chave de desenvolvimento não é usada em produção.')
    SECRET_KEY = SECRET_KEY_DESENVOLVIMENTO
elif not DEBUG and SECRET_KEY == SECRET_KEY_DESENVOLVIMENTO:
    raise ImproperlyConfigured('DEBUG=0 com a chave de desenvolvimento: defina uma DJANGO_SECRET_KEY própria.')

# Local: qualquer host. Produção: lista separada por vírgula em DJANGO_ALLOWED_HOSTS; sem ela, nenhum host é aceito
# (o Django responde 400), exceto /healthz, que responde antes da validação de host (desafio_itau/saude.py).
ALLOWED_HOSTS = _env_lista('DJANGO_ALLOWED_HOSTS', 'ALLOWED_HOSTS') or (['*'] if DEBUG else [])

if not DEBUG:
    # O Cloud Run termina o TLS e repassa o pedido em HTTP com X-Forwarded-Proto: https.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_COOKIE_SECURE = True

# Application definition
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    # App principal de recomendação e contextualização de agentes
    'apps.recomendacao',
    # Novo app: context-agent-datadriven com comunicação via secret gsconsole
    'apps.context_agent_datadriven',
    # Planejamento i-agora (porte de Frontend/agent_backend/planning, 2026-09-27): perfil, plano, confirmar
    'apps.i_agora',
]

MIDDLEWARE = [
    # /healthz responde aqui, antes do CORS e da validação de host: não toca em banco, BigQuery nem Gemini.
    'desafio_itau.saude.HealthzMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'desafio_itau.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'templates' / 'recommendations',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'desafio_itau.wsgi.application'
ASGI_APPLICATION = 'desafio_itau.asgi.application'

# Configuração do banco de dados SQLite persistente
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # SQLITE_PATH: no contêiner aponta para /tmp (disco efêmero; a sessão some a cada revisão, ver §5 das decisões).
        'NAME': _env('SQLITE_PATH') or BASE_DIR / 'db.sqlite3',
    }
}

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
] if (BASE_DIR / 'static').exists() else []

# Origens do front aceitas por CORS e CSRF (Decisão D-5, 2026-09-27): localhost e 127.0.0.1 nas portas 3000 e 3001.
# FRONT_ORIGENS (lista separada por vírgula) substitui o padrão; qualquer outra porta fica de fora.
# CORS_ALLOW_ALL=1 reabre o CORS para qualquer origem (antes da D-5 era o padrão); não afeta o CSRF.
FRONT_ORIGENS_PADRAO = [
    f'http://{host}:{porta}' for porta in (3000, 3001) for host in ('localhost', '127.0.0.1')
]
FRONT_ORIGENS = [
    o.strip().rstrip('/') for o in os.environ.get('FRONT_ORIGENS', '').split(',') if o.strip()
] or FRONT_ORIGENS_PADRAO
CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL', '0').strip().lower() in ('1', 'true', 'sim', 'on')
CORS_ALLOWED_ORIGINS = FRONT_ORIGENS

# Sem django.contrib.auth instalado: o DRF não pode montar AnonymousUser,
# senão toda APIView responde 500 antes de chegar à view.
REST_FRAMEWORK = {
    'UNAUTHENTICATED_USER': None,
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
}

# Configurações do Engine de Contextualização e Agente
SCORE_CONFIG = {
    'TOTAL_CUSTOMERS': 1000,
    'SCORE_MIN': 0,
    'SCORE_MAX': 1000,
    'INDEX_CUTOFF_HIGH': 750,
    'INDEX_CUTOFF_MED': 450,
}

# Fonte "usuário real": extrato no BigQuery, lido com ADC (gcloud auth application-default login).
# ON por padrão; USUARIO_REAL_ATIVO=0 desliga e as rotas /usuario-real/ respondem 503 com estado OFF.
USUARIO_REAL = {
    'ATIVO': os.environ.get('USUARIO_REAL_ATIVO', '1').strip().lower() not in ('0', 'false', 'off', 'nao'),
    'PROJETO': os.environ.get('USUARIO_REAL_PROJETO', 'batalha-time-02-lxof'),
    'TABELA': 'batalha-time-02-lxof.hackathon_dados.extrato_sintetico',
    'DATA_CORTE': '2025-12-22',
    'CACHE_SEGUNDOS': int(os.environ.get('USUARIO_REAL_CACHE_SEGUNDOS', '900')),
}

# Conversa i-agora (apps/conversas, porte de agente-app-mobile/agent_backend). Contrato: docs/contrato-api-frontend.md, 5.2.
# MODO: 'demo_live' chama o Gemini (chave de desafio_itau/segredos.py); 'demo' devolve texto fixo, sem IA.
# MAX_CHAMADAS: orçamento de chamadas ao Gemini por processo (cada mensagem gasta 3: guard de entrada, gerador, guard de saída).
CONVERSAS = {
    'MODO': os.environ.get('CONVERSAS_MODO', 'demo_live'),
    'MAX_CHAMADAS': min(max(int(os.environ.get('CONVERSAS_MAX_CHAMADAS', '300')), 0), 3000),
}
# Front de agente-app-mobile (Vite na porta 3000 ou 3001, proxy para o Django): o CSRF confere a Origin.
# Mesma lista do CORS (FRONT_ORIGENS, acima). Decisão D-5, 2026-09-27.
CSRF_TRUSTED_ORIGINS = list(FRONT_ORIGENS)
# Produção: origens extras só para o CSRF (ex.: a URL https:// do próprio serviço), sem abrir o CORS.
for _origem in _env_lista('DJANGO_CSRF_TRUSTED_ORIGINS', 'CSRF_TRUSTED_ORIGINS') or []:
    if _origem.rstrip('/') not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origem.rstrip('/'))
