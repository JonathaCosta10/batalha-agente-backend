"""
Pacote LLM_Models contendo os provedores:
- google
- antropic
- openIa
"""
from .google.cliente import GoogleLLMCliente
from .antropic.cliente import AntropicLLMCliente
from .openIa.cliente import OpenIaLLMCliente

PROVEDORES_REGISTRADOS = {
    "google": GoogleLLMCliente,
    "antropic": AntropicLLMCliente,
    "openIa": OpenIaLLMCliente,
}
