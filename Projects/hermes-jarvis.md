# Projeto Hermes Jarvis

## Visão Geral

Transformar o Hermes Agent em um assistente pessoal estilo Jarvis, com memória persistente, automações locais e integração total com o ecossistema do usuário.

## Pilares

1. **Memória Persistente**: Dados cruzados entre Obsidian e Hermes
2. **Automações Locais**: Scripts e workflows automatizados
3. **Integração Multi-ferramenta**: MCP, skills, providers
4. **Interface Natural**: CLI-first, sem complicação

## Estrutura JARVIS

```
JARVIS/
├── Memory/           # Perfil, objetivos, contexto
├── Projects/         # Projetos ativos e seus estados
├── Learnings/        # Padrões descobertos, lições
├── Prompts/          # System prompts, templates
├── Skills/           # Skills customizadas do Jarvis
├── Configs/          # Configs versionadas
└── Logs/             # Histórico de execuções
```

## Status do Sistema

| Componente | Estado | Próximos Passos |
|---|---|---|
| Obsidian Vault | Conectado | Expandir estrutura |
| 85 Skills | Ativas | Mapear uso real |
| MCP Servers | Não configurado | Adicionar servidores úteis |
| Ollama Local | Rodando (2 modelos) | Testar fallback local |
| Leonardo.ai | Script pronto | Automatizar geração |
| Dola AI | Script pronto | Automatizar geração |
