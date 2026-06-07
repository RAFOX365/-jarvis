# JARVIS System

Core pessoal estilo Jarvis, orquestrado pelo Hermes Agent e com memória persistente no Obsidian.

## Estrutura

```
JARVIS/
├── Memory/           # Perfil, contexto, estado do sistema
├── Projects/         # Projetos ativos e seus status
├── Learnings/        # Padrões descobertos e lições
├── Prompts/          # System prompts reutilizáveis
├── Skills/           # Skills customizadas do sistema
├── Configs/          # Configurações versionadas
├── Logs/             # Histórico e auditoria
├── Snapshots/        # Backups automáticos do vault
└── Index/            # Navegação central
```

## Core Python

`Skills/obsidian-brain.py` — `ObsidianBrainV2`

Responsável por toda a manipulação do vault: escrita, append, busca, snapshot, tags, verificação e estatísticas.

### Funções disponíveis

| Função | Descrição | Retorno |
|---|---|---|
| `__init__(vault_path)` | Inicializa core, garante estrutura e cria Index | — |
| `ensure_structure()` | Recria pastas base | None |
| `file_hash(path)` | SHA-256 real do arquivo | `str | None` |
| `write_note(folder, filename, content)` | Escreve/sobrescreve nota com auditoria | `str` (path) |
| `append_note(folder, filename, content)` | Append sem sobrescrever | `str` (path) |
| `log(event, data)` | Log auditável com host/user/version | `dict` |
| `snapshot(keep=5)` | Snapshot completo + retenção + `_latest` | `str` (path) |
| `search(query)` | Busca case-insensitive por string | `list[str]` |
| `search_with_context(query, max_results, context_chars)` | Busca com snippet ao redor do match | `list[dict]` |
| `list_notes(folder)` | Lista `.md` de uma pasta | `list[str]` |
| `list_folders()` | Lista pastas do vault | `list[str]` |
| `get_stats()` | Métricas do vault | `dict` |
| `cleanup_logs(keep=10)` | Limpa logs antigos | `int` (linhas mantidas) |
| `add_tag(folder, filename, tag)` | Adiciona tag Obsidian | `str` (path) |
| `remove_tag(folder, filename, tag)` | Remove tag Obsidian | `str` (path) |
| `verify_vault()` | Verifica integridade | `dict` |
| `init_rafox()` | Inicializa `Memory/rafox.md` | `str` (path) |

### Exemplo rápido

```python
from obsidian-brain import ObsidianBrainV2

brain = ObsidianBrainV2()

# Escrever memória
brain.write_note("Memory", "resumo", "# Resumo\nConteúdo...")

# Buscar com contexto
for hit in brain.search_with_context("cannabis", max_results=3):
    print(hit["snippet"], hit["path"])

# Snapshot seguro
brain.snapshot(keep=3)

# Estatísticas
print(brain.get_stats())
```

## Auditoria

- Logs em `Logs/audit.log.md`
- Cada operação registra: timestamp, host, usuário, versão do core
- Snapshot rotativo em `Snapshots/` com `_latest` sempre atualizado

## Status do Sistema

| Componente | Estado |
|---|---|
| Vault Obsidian | Conectado |
| Core Python | v2.1.0 |
| 85 Skills | Ativas |
| MCP Servers | Não configurado |
| Ollama Local | Rodando (2 modelos) |
| Leonardo.ai | Script pronto |
| Dola AI | Script pronto |

## Próximos Passos

- Configurar MCP servers úteis
- Integrar `obsidian-brain.py` com skills existentes
- Automatizar backup para nuvem (opcional)
- Expandir Learnings com padrões reais do Hermes
