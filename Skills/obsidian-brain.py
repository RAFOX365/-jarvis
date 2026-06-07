import os
import sys
import hashlib
import shutil
import platform
from pathlib import Path
from datetime import datetime

VAULT_PATH = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
__version__ = "2.1.0"

class ObsidianBrainV2:
    def __init__(self, vault_path=VAULT_PATH):
        self.vault = Path(vault_path).resolve()
        self.host = platform.node()
        self.user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
        self.folders = [
            "Memory", "Projects", "Learnings",
            "Prompts", "Skills", "Configs",
            "Logs", "Snapshots", "Index"
        ]
        self.ensure_structure()
        self._bootstrap_index()

    # ----------------------------
    # ESTRUTURA BASE
    # ----------------------------
    def ensure_structure(self):
        for f in self.folders:
            (self.vault / f).mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # UTILITÁRIOS
    # ----------------------------
    def _now_iso(self):
        return datetime.now().isoformat()

    def _now_stamp(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _safe_within_vault(self, target: Path) -> bool:
        try:
            target.resolve().relative_to(self.vault.resolve())
            return True
        except ValueError:
            return False

    # ----------------------------
    # HASH (VERIFICAÇÃO REAL)
    # ----------------------------
    def file_hash(self, path):
        p = Path(path)
        if not p.exists():
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()

    # ----------------------------
    # WRITE COM VERIFICAÇÃO + AUDITORIA
    # ----------------------------
    def write_note(self, folder, filename, content):
        path = self.vault / folder / f"{filename}.md"

        if not self._safe_within_vault(path):
            raise ValueError(f"Path fora do vault: {path}")

        before_hash = self.file_hash(path)
        existed = path.exists()

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        after_hash = self.file_hash(path)

        self.log("WRITE_NOTE", {
            "file": str(path),
            "before": before_hash,
            "after": after_hash,
            "action": "UPDATE" if existed else "CREATE",
            "verified": before_hash != after_hash
        })

        return str(path)

    # ----------------------------
    # APPEND SEGURO
    # ----------------------------
    def append_note(self, folder, filename, content):
        path = self.vault / folder / f"{filename}.md"

        if not self._safe_within_vault(path):
            raise ValueError(f"Path fora do vault: {path}")

        old_hash = self.file_hash(path)

        current = ""
        if path.exists():
            current = path.read_text(encoding="utf-8")

        updated = current + "\n\n" + content
        path.write_text(updated, encoding="utf-8")

        new_hash = self.file_hash(path)

        self.log("APPEND_NOTE", {
            "file": str(path),
            "old_hash": old_hash,
            "new_hash": new_hash
        })

        return str(path)

    # ----------------------------
    # LOG AUDITÁVEL
    # ----------------------------
    def log(self, event, data):
        now = self._now_iso()
        payload = {
            "timestamp": now,
            "event": event,
            "data": data,
            "host": self.host,
            "user": self.user,
            "version": __version__
        }
        log_entry = f"""
[{now}] {event}
DATA: {data}
HOST: {self.host}
USER: {self.user}
VERSION: {__version__}
"""
        log_path = self.vault / "Logs" / "audit.log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        return payload

    # ----------------------------
    # SNAPSHOT DO VAULT (ROTATIVO)
    # ----------------------------
    def snapshot(self, keep: int = 5):
        now = self._now_stamp()
        snap_path = self.vault / "Snapshots" / f"snapshot_{now}"
        shutil.copytree(self.vault, snap_path, ignore=shutil.ignore_patterns("Snapshots"))

        latest = self.vault / "Snapshots" / "_latest"
        if latest.exists():
            shutil.rmtree(latest)
        shutil.copytree(snap_path, latest)

        self._cleanup_snapshots(keep=keep)

        self.log("SNAPSHOT", {
            "snapshot_path": str(snap_path),
            "latest": str(latest),
            "keep": keep
        })
        return str(snap_path)

    # ----------------------------
    # BUSCA SIMPLES
    # ----------------------------
    def search(self, query):
        results = []
        for path in self.vault.rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    results.append(str(path))
            except Exception:
                pass

        self.log("SEARCH", {
            "query": query,
            "results": len(results)
        })
        return results

    # ----------------------------
    # BUSCA COM CONTEXTO
    # ----------------------------
    def search_with_context(self, query: str, max_results: int = 5, context_chars: int = 180):
        hits = []
        needle = query.lower()
        for path in self.vault.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
                idx = text.lower().find(needle)
                if idx != -1:
                    start = max(0, idx - context_chars)
                    end = min(len(text), idx + len(query) + context_chars)
                    snippet = text[start:end].replace("\n", " ")
                    hits.append({
                        "path": str(path),
                        "snippet": snippet
                    })
            except Exception:
                pass

        hits = hits[:max_results]
        self.log("SEARCH_CONTEXT", {
            "query": query,
            "max_results": max_results,
            "context_chars": context_chars,
            "results": len(hits)
        })
        return hits

    # ----------------------------
    # LISTAGENS
    # ----------------------------
    def list_notes(self, folder: str):
        folder_path = self.vault / folder
        if not folder_path.exists():
            return []
        return [
            str(p.relative_to(self.vault))
            for p in sorted(folder_path.rglob("*.md"))
            if p.is_file()
        ]

    def list_folders(self):
        return sorted([
            str(p.relative_to(self.vault))
            for p in self.vault.iterdir()
            if p.is_dir()
        ])

    # ----------------------------
    # ESTATÍSTICAS
    # ----------------------------
    def get_stats(self):
        md_files = list(self.vault.rglob("*.md"))
        total_size = sum(p.stat().st_size for p in md_files if p.exists())
        return {
            "total_notes": len(md_files),
            "folders": len([p for p in self.vault.iterdir() if p.is_dir()]),
            "total_size_bytes": total_size,
            "vault_path": str(self.vault),
            "version": __version__
        }

    # ----------------------------
    # LIMPEZA AUTOMÁTICA
    # ----------------------------
    def _cleanup_snapshots(self, keep: int = 5):
        snap_dir = self.vault / "Snapshots"
        if not snap_dir.exists():
            return
        items = sorted(
            [p for p in snap_dir.iterdir() if p.is_dir() and p.name != "_latest"],
            key=lambda p: p.name,
            reverse=True
        )
        for old in items[keep:]:
            shutil.rmtree(old, ignore_errors=True)

    def cleanup_logs(self, keep: int = 10):
        log_path = self.vault / "Logs" / "audit.log.md"
        if not log_path.exists():
            return 0
        lines = log_path.read_text(encoding="utf-8").splitlines()
        keep_lines = []
        count = 0
        for line in lines:
            if line.strip().startswith("[") and line.strip().endswith("]"):
                count += 1
                if count > (len(lines) - keep):
                    keep_lines.append(line)
            else:
                if keep_lines:
                    keep_lines.append(line)
        log_path.write_text("\n".join(keep_lines) + "\n", encoding="utf-8")
        return count

    # ----------------------------
    # TAGS GERENCIADAS
    # ----------------------------
    def add_tag(self, folder: str, filename: str, tag: str):
        path = self.vault / folder / f"{filename}.md"
        if not path.exists():
            raise FileNotFoundError(path)
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        tag_line = f"#{tag}"
        frontmatter_end = 0
        if lines and lines[0].strip() == "---":
            in_fm = True
            for i, line in enumerate(lines):
                if in_fm and line.strip() == "---" and i > 0:
                    in_fm = False
                    frontmatter_end = i
                    new_lines.append(f"tags: [{tag}]")
                    new_lines.append(line)
                    continue
                new_lines.append(line)
        else:
            new_lines = lines
            new_lines.append("")
            new_lines.append(tag_line)

        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        self.log("ADD_TAG", {"file": str(path), "tag": tag})
        return str(path)

    def remove_tag(self, folder: str, filename: str, tag: str):
        path = self.vault / folder / f"{filename}.md"
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        text = text.replace(f"#{tag}", "").replace(f"tags: [{tag}]", "tags: []")
        path.write_text(text, encoding="utf-8")
        self.log("REMOVE_TAG", {"file": str(path), "tag": tag})
        return str(path)

    # ----------------------------
    # VERIFICAÇÃO DE INTEGRIDADE
    # ----------------------------
    def verify_vault(self):
        report = {
            "total_files": 0,
            "missing_files": [],
            "corrupted": [],
            "last_check": self._now_iso()
        }

        for path in self.vault.rglob("*.md"):
            report["total_files"] += 1
            if not path.exists():
                report["missing_files"].append(str(path))
            else:
                try:
                    path.read_text(encoding="utf-8")
                except Exception:
                    report["corrupted"].append(str(path))

        self.log("VERIFY_VAULT", report)
        return report

    # ----------------------------
    # INDEX INICIAL
    # ----------------------------
    def _bootstrap_index(self):
        if (self.vault / "Index" / "README.md").exists():
            return
        content = f"""# JARVIS Index

Inicializado em: {self._now_iso()}
Versão do core: {__version__}

## Pastas
{chr(10).join(f'- [[{f}]]' for f in self.folders)}

## Notas recentes
{chr(10).join(f'- [[{n}]]' for n in self.list_notes("Memory")[:5])}
"""
        self.write_note("Index", "README", content)

    # ----------------------------
    # INIT RAFOX CORE
    # ----------------------------
    def init_rafox(self):
        content = f"""# Rafox Core

## Sistema
Windows (host local)

## Estado
Obsidian Brain V2 ativo (v{__version__})

## Capacidades
- logs auditáveis
- snapshots
- busca com contexto
- verificação de integridade
- gerenciamento de tags
- estatísticas do vault
- indexação automática
"""
        return self.write_note("Memory", "rafox", content)


    # ----------------------------
    # WRAPPERS PARA SKILL SYSTEM (módulo-level)
    # ----------------------------
    def _reload():
        return importlib.reload(sys.modules[__name__])

    def _info():
        return {
            "skill": "obsidian-brain",
            "version": __version__,
            "vault": str(VAULT_PATH),
            "actions": [
                "write_note", "append_note", "read_note",
                "list_notes", "list_folders", "search",
                "search_with_context", "snapshot", "verify_vault",
                "add_tag", "remove_tag", "get_stats", "init_rafox",
                "reload", "info"
            ]
        }


# Instância default usada pelos wrappers
_default = ObsidianBrainV2()

# Wrappers de módulo para skill system
def write_note(folder, filename, content):
    return _default.write_note(folder, filename, content)

def append_note(folder, filename, content):
    return _default.append_note(folder, filename, content)

def read_note(folder, filename):
    return _default.read_note(folder, filename)

def list_notes(folder):
    return _default.list_notes(folder)

def list_folders():
    return _default.list_folders()

def search(query):
    return _default.search(query)

def search_with_context(query, max_results=5, context_chars=180):
    return _default.search_with_context(query, max_results, context_chars)

def snapshot(keep=5):
    return _default.snapshot(keep=keep)

def verify_vault():
    return _default.verify_vault()

def add_tag(folder, filename, tag):
    return _default.add_tag(folder, filename, tag)

def remove_tag(folder, filename, tag):
    return _default.remove_tag(folder, filename, tag)

def get_stats():
    return _default.get_stats()

def init_rafox():
    return _default.init_rafox()

def reload():
    return _reload()

def info():
    return _info()


# ----------------------------
# TESTE
# ----------------------------
if __name__ == "__main__":
    brain = ObsidianBrainV2()

    brain.init_rafox()

    brain.append_note("Learnings", "index", "Sistema atualizado para versão V2")

    brain.snapshot()

    print(brain.search("Obsidian"))

    print(brain.verify_vault())
