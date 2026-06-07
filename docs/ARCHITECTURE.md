# Arquitetura do JARVIS

## Camadas
- Core: `JarvisCore` (evento/skills/logs)
- Skills: módulos plugáveis em `Skills/`
- Memória: Obsidian vault (`JARVIS/`)

## Fluxo
Load -> Event -> Skill -> Log -> Snapshot

## Diagrama (ASCII)
[JARVIS Core]
    |
    +-- EventEmitter
    +-- SkillRegistry
    +-- SafeLogger
    +-- ObsidianFS / GitOps
    |
    v
[Obsidian Vault]
