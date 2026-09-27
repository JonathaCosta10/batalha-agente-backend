"""ASGI do projeto desafio_itau (referenciado por settings.ASGI_APPLICATION)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'desafio_itau.settings')

application = get_asgi_application()
