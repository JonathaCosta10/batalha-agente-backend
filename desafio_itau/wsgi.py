"""WSGI do projeto desafio_itau (referenciado por settings.WSGI_APPLICATION)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'desafio_itau.settings')

application = get_wsgi_application()
