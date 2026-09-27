# desafio-itau-batalha-de-agentes-time2

Repositório do Backend Django e Motor de Contextualização para a Batalha de Agentes Itaú (Time 2).

## Estrutura do Projeto
- `desafio_itau/`: Configuração principal do Django (settings, urls, wsgi, asgi).
- `apps/recomendacao/`: Aplicativo Django com views, repositório de 1.000 clientes, cálculo de índice comportamental e templates.
- `apps/context_agent_datadriven/`: **Novo aplicativo Django** para comunicação com o Agente de IA contextualizado orientado a dados, com a chave lida por `desafio_itau/segredos.py` (`API_KEY_SECRECT` no `.secrets` da raiz da solução; legado `GEMINI_API_KEY` / `GSCONSOLE_SECRET` / `GOOGLE_API_KEY`).
  - `services/primeira_chamada.py`: Chamada direta ao Gemini com apenas o texto inicial (usada pelo front).
  - `services/agente_service.py`: Motor de envio de mensagem, prompt de sistema baseado em dados do cliente e recebimento de resposta da IA.
  - `views.py`: Endpoints REST (`/status-harness/`, `/enviar-mensagem/`, `/primeira-chamada/`) e painel web.
  - `models.py`: Registro de sessões, mensagens trocadas e credenciais.
- `templates/`: Templates HTML para F/M (`chat_f.html`, `chat_m.html`), neutro e matriz fixa (`template_3_matrix.html`).
- `docs/`: Documentação da arquitetura, dos fluxos entre telas (`fluxos-de-conversacao.md`), do ponto de índice comportamental, dos templates e dos contratos JSON Schema (`inteirações-cloud/`).
- `notebooks/`: Jupyter Notebook `regras_batalha_agentes.ipynb` para prototipação e inserção das regras de negócio adicionais.

## Como Executar o Backend Django
```bash
cd desafio-itau-batalha-de-agentes-time2
pip install -r requirements.txt
python manage.py runserver 8000
```
Ao acessar `http://localhost:8000/`, a aplicação redireciona automaticamente para o app de recomendação (`/app/`) e disponibiliza `/context-agent/` e `/api/v1/context-agent/`.
