"""
Templates HTML para o aplicativo context-agent-datadriven.
"""

from django.http import HttpResponse

HTML_PAINEL = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Itaú · context-agent-datadriven</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen p-6 font-sans">
    <div class="max-w-4xl mx-auto space-y-6">
        <header class="border-b border-slate-800 pb-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <span class="w-9 h-9 rounded-xl bg-[#EC7000] text-white flex items-center justify-center font-bold text-lg">i</span>
                <div>
                    <h1 class="text-lg font-bold text-white">App Django: context-agent-datadriven</h1>
                    <p class="text-xs text-slate-400">Comunicação e Contextualização com Agente de IA via Secret gsconsole</p>
                </div>
            </div>
            <span class="px-3 py-1 bg-slate-800 text-slate-200 border border-slate-600 rounded-full text-xs font-mono">
                Chave: {{ESTADO_CHAVE}} (não testada)
            </span>
        </header>

        <main class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4">
                <h2 class="text-sm font-semibold text-orange-400 font-mono">Chave do agente</h2>
                <div class="text-xs space-y-2 text-slate-300">
                    <p><strong>Leitura:</strong> desafio_itau/segredos.py (API_KEY_SECRECT no ambiente ou no .secrets da raiz; legado GEMINI_API_KEY / GSCONSOLE_SECRET / GOOGLE_API_KEY)</p>
                    <p><strong>Estado:</strong> {{ESTADO_CHAVE}} — CONFIGURADA quer dizer que a chave existe, não que a Google a aceita. Este painel não faz chamada de rede.</p>
                    <p><strong>Validar de verdade:</strong> GET /api/v1/context-agent/status-harness/?validar=1 → VALIDADA / INVALIDA / NAO_MEDIDO</p>
                    <p><strong>Modelo:</strong> gemini-flash-latest / gemini-3.5-flash-lite</p>
                </div>
            </div>

            <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4">
                <h2 class="text-sm font-semibold text-orange-400 font-mono">Endpoints REST Disponíveis</h2>
                <div class="text-xs font-mono space-y-2 text-slate-300">
                    <p class="p-2 bg-slate-900 rounded border border-slate-800">
                        <strong class="text-emerald-400">GET</strong> /api/v1/context-agent/status-harness/
                    </p>
                    <p class="p-2 bg-slate-900 rounded border border-slate-800">
                        <strong class="text-amber-400">POST</strong> /api/v1/context-agent/conversas/interacao/
                    </p>
                </div>
            </div>
        </main>
    </div>
</body>
</html>
"""
