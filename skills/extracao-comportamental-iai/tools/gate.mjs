// Pre-guard offline da extracao-comportamental-iai (Node, sem BigQuery).
// Uso:
//   node tools/gate.mjs                                   -> evals golden/adversarial + scripts/testar_skill.py
//   node tools/gate.mjs --proposta p.json --evidencia e.json -> so a forma e os fatos da proposta contra a evidencia
// Espelha as regras estruturais de scripts/validar_resposta.py; a RELEITURA do BigQuery continua so no Python.
// Saida: 0 = TUDO OK / APROVADO; 1 = REPROVADO ou eval falhou; 2 = NAO_MEDIDO (ex.: sem Python).
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const skill = resolve(aqui, "..");
const raizBackend = resolve(skill, "..", "..");
const lerJson = (p) => JSON.parse(readFileSync(p, "utf8"));

function politica() {
  const out = {};
  for (const linha of readFileSync(join(skill, "policies", "gates.yaml"), "utf8").split(/\r?\n/)) {
    const m = linha.match(/^([a-z_]+):\s*(.+?)\s*$/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

const POL = politica();
const CONTRATO = lerJson(join(skill, POL.contrato));
const UUID = new RegExp(POL.uuid_regex);
const tipo = (v) => (Number.isInteger(v) ? "int" : typeof v === "number" ? "float" : typeof v);

// Devolve null quando aprova, ou o motivo da recusa (mesmas frases do guard Python quando existem).
export function preGuard(proposta, evidencia) {
  const campos = CONTRATO.proposta_do_agente.campos_exatos;
  if (!proposta || typeof proposta !== "object" || Array.isArray(proposta)) return "proposta nao e objeto JSON";
  const chaves = Object.keys(proposta).sort().join(",");
  if (chaves !== [...campos].sort().join(",")) return "estrutura JSON da proposta diverge do contrato";
  for (const k of ["id_extracao", "id_usuario", "comportamento", "categoria", "campo"])
    if (typeof proposta[k] !== "string") return "tipos da proposta divergem do contrato";
  if (!["string", "number"].includes(typeof proposta.valor)) return "tipo do valor diverge do contrato";
  if (!Number.isInteger(proposta.numero_usuario)) return "numero do usuario nao e inteiro";
  if (!UUID.test(proposta.id_usuario)) return "id_usuario nao e UUID canonico";
  const sel = evidencia?.selecao;
  if (!sel || !sel.linha) return "evidencia sem selecao";
  if (sel.campo !== CONTRATO.extracao.campo_de_valor) return "campo nao contratado";
  const esperado = {
    id_extracao: evidencia.id_extracao, numero_usuario: sel.numero_usuario, id_usuario: sel.id_usuario,
    comportamento: CONTRATO.extracao.comportamento[sel.linha.tipo], categoria: sel.linha.nom_cate_macro,
    campo: sel.campo, valor: sel.linha[sel.campo],
  };
  for (const [k, v] of Object.entries(esperado))
    if (tipo(proposta[k]) !== tipo(v) || proposta[k] !== v) return "proposta contem fato diferente do extrato";
  return null;
}

function casos(pasta) {
  const dir = join(skill, "evals", pasta);
  return existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".json")).sort().map((f) => ({ f: `${pasta}/${f}`, ...lerJson(join(dir, f)) })) : [];
}

function evals() {
  const todos = [...casos("golden"), ...casos("adversarial")];
  let ok = 0, negativas = 0, apanhadas = 0;
  for (const c of todos) {
    const motivo = preGuard(c.proposta, c.evidencia);
    const reprovou = motivo !== null;
    const deveReprovar = c.deve === "reprovar";
    if (deveReprovar) negativas++;
    const certo = deveReprovar ? reprovou && (!c.falha_contem || motivo.includes(c.falha_contem)) : !reprovou;
    if (certo) { ok++; if (deveReprovar) apanhadas++; }
    console.log(`${certo ? "ok   " : "FALHA"} ${c.f}: ${reprovou ? POL.esperado_adversarial + " (" + motivo + ")" : POL.esperado_golden}`);
  }
  if (!negativas) { console.log("FALHA: nenhum caso adversarial (prova negativa ausente)"); return false; }
  const tudo = ok === todos.length;
  console.log(tudo ? `TUDO OK — ${ok}/${todos.length} casos, ${apanhadas}/${negativas} provas negativas apanhadas`
    : `FALHA — ${ok}/${todos.length} casos, ${apanhadas}/${negativas} provas negativas apanhadas`);
  return tudo;
}

function unittestPython() {
  const candidatos = [process.env.PYTHON, join(raizBackend, ".venv", "Scripts", "python.exe"),
    join(raizBackend, ".venv", "bin", "python")].filter(Boolean);
  const python = candidatos.find((p) => existsSync(p));
  if (!python) { console.log("NAO_MEDIDO: nenhum Python do backend encontrado (defina PYTHON) — scripts/testar_skill.py nao rodou"); return 2; }
  const r = spawnSync(python, [join(skill, POL.python_testes)], { cwd: join(skill, "scripts"), stdio: "inherit" });
  return r.status === 0 ? 0 : r.status === null ? 2 : 1;
}

const args = process.argv.slice(2);
const valor = (nome) => { const i = args.indexOf(nome); return i >= 0 ? args[i + 1] : undefined; };
if (valor("--proposta") || valor("--evidencia")) {
  if (!valor("--proposta") || !valor("--evidencia")) { console.log("NAO_MEDIDO: passe --proposta e --evidencia"); process.exit(2); }
  const motivo = preGuard(lerJson(valor("--proposta")), lerJson(valor("--evidencia")));
  console.log(motivo ? `REPROVADO: ${motivo}` : "APROVADO (pre-guard offline; rode scripts/validar_resposta.py para a releitura BigQuery)");
  process.exit(motivo ? 1 : 0);
} else {
  const okEvals = evals();
  const py = args.includes("--sem-python") ? 0 : unittestPython();
  process.exit(!okEvals ? 1 : py);
}
