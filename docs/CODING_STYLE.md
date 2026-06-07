# CODING_STYLE.md

Guia de estilo e disciplina para contribuir no JARVIS.

## Princípios
- Pequenos commits com mensagens claras.
- Zero dependência externa obrigatória.
- Logs JSONL, nunca texto solto.

## Convenções
- Funções retornam `{"ok": bool, "path": str, "data": Any, "error": str}`.
- Erros nunca viram exceção silenciosa.
- skills são módulos isolados em `Skills/`.

## Commits
Use Conventional Commits:
- feat: nova funcionalidade
- fix: correção
- docs: documentação
- chore: manutenção/refatoração
- test: testes (se existirem)
