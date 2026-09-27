# Origem da cópia local — estudo i.agora

| Campo | Valor |
| --- | --- |
| Arquivo local | `i.agora-checkpoint.ipynb` (cópia byte a byte, sem edição) |
| Fonte | Google Colab `https://colab.research.google.com/drive/12DmuaPBmv-qDVvfvAvxczSFVB8K4hfr6` |
| ID no Drive | `12DmuaPBmv-qDVvfvAvxczSFVB8K4hfr6` |
| Título no Drive | `i.agora-checkpoint.ipynb` |
| Dono no Drive | conta da colega autora do estudo (e-mail omitido) |
| Criado no Drive | 2026-09-27T00:50:56Z |
| Última modificação no Drive | 2026-09-27T06:34:48Z |
| Baixado em | 2026-09-27 03:42 BRT, por download público do Drive |
| Tamanho | 2.063.197 bytes |
| SHA-256 | `b4419b23d7aa02d931c92db6825a9a496bbe037c3546ee9b4891a10124a4b0c5` |
| Kernel declarado | `Python [conda env:base]` |
| Células | 41 (21 código, 20 markdown), com saídas e gráficos gravados |

## O que a cópia contém e o que falta

- As saídas foram gravadas na máquina de quem executou o estudo. **Esta cópia não foi reexecutada.**
- A base real (`bq-results-20260926-143453-1790433308679.csv`, exportação do BigQuery) **não veio junto**. O notebook lê esse CSV de `C:\Users\lostj\...`, caminho que não existe aqui.
- Por isso, a maioria das consultas roda com dados sintéticos (`np.random.seed(42)`) ou com um *fallback* de contagens fixas no código. A classificação de cada consulta está em [`docs/estudo-i-agora/consultas.md`](../../docs/estudo-i-agora/consultas.md).

## Para atualizar

Baixe outra vez pelo mesmo ID, grave uma versão com data ao lado desta, registre o novo SHA-256 nesta tabela e mova a anterior para `notebooks/estudo-i-agora/archive/<AAAA-MM-DD>/` com uma linha em `archive/INDICE.md`. Nada é excluído.
