import os
import sys
import importlib.util
import json
import platform
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

VAULT = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
SKILLS_PATH = Path(VAULT) / "Skills"
LOG_PATH = Path(VAULT) / "Logs" / "core.log.jsonl"
__version__ = "3.1.0"


# -------------------------
# UTIL
# -------------------------
def now():
    return datetime.now().isoformat()


def _truncate(value: str, max_chars: int = 500) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...[truncated]"


# -------------------------
# CORE ENGINE
# -------------------------
class JarvisCore:

    def __init__(self, vault_path: str = VAULT):
        self.vault = Path(vault_path).resolve()
        self.skills_path = self.vault / "Skills"
        self.skills: Dict[str, Any] = {}
        self.host = platform.node()
        self.user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
        self.load_skills()

    # -------------------------
    # LOAD SKILLS DINAMICAMENTE
    # -------------------------
    def load_skills(self):
        if not self.skills_path.exists():
            self.skills_path.mkdir(parents=True, exist_ok=True)

        for file in sorted(self.skills_path.glob("*.py")):
            name = file.stem

            if name.startswith("__"):
                continue

            try:
                spec = importlib.util.spec_from_file_location(f"jarvis_skill_{name}", file)
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                self.skills[name] = module
                self._log("SKILL_LOADED", {"skill": name, "file": str(file)})
            except Exception as e:
                self._log("SKILL_FAIL", {
                    "skill": name,
                    "error": str(e),
                    "file": str(file)
                })

    # -------------------------
    # RELOAD SKILLS
    # -------------------------
    def reload_skills(self) -> Dict[str, str]:
        results = {}
        for name, module in list(self.skills.items()):
            try:
                importlib.reload(module)
                results[name] = "reloaded"
            except Exception as e:
                results[name] = f"error: {str(e)}"
        self._log("SKILL_RELOAD", results)
        return results

    # -------------------------
    # EXECUTOR DE SKILL
    # -------------------------
    def run_skill(self, skill_name: str, action: str, **kwargs) -> Any:
        if not self._valid_skill_name(skill_name):
            error = f"invalid_skill_name: {skill_name}"
            self._log("SKILL_EXEC_ERROR", error)
            return {"error": error}

        if skill_name not in self.skills:
            error = f"skill_not_found: {skill_name}"
            self._log("SKILL_EXEC_ERROR", error)
            return {"error": error}

        skill = self.skills[skill_name]

        if not hasattr(skill, action):
            available = [
                m for m in dir(skill)
                if not m.startswith("_") and callable(getattr(skill, m))
            ]
            error = {
                "error": "action_not_found",
                "action": action,
                "available_actions": available
            }
            self._log("SKILL_EXEC_ERROR", error)
            return error

        try:
            method = getattr(skill, action)
            result = method(**kwargs)
            self._log("SKILL_EXEC", {
                "skill": skill_name,
                "action": action,
                "args": kwargs,
                "result": _truncate(str(result), 500)
            })
            return result
        except TypeError as e:
            error = {
                "error": "invalid_args",
                "detail": str(e)
            }
            self._log("SKILL_EXEC_ERROR", error)
            return error
        except Exception as e:
            error = {
                "error": "exec_exception",
                "detail": str(e)
            }
            self._log("SKILL_EXEC_ERROR", error)
            return error

    # -------------------------
    # LISTAGENS
    # -------------------------
    def list_skills(self) -> List[str]:
        return sorted(self.skills.keys())

    # -------------------------
    # LOG INTERNO
    # -------------------------
    def _log(self, event: str, data: Any):
        entry = {
            "time": now(),
            "event": event,
            "data": data,
            "host": self.host,
            "user": self.user,
            "version": __version__
        }

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry


    def _valid_skill_name(self, name: str) -> bool:
        if not name:
            return False
        if name.startswith(".") or name.startswith("_"):
            return False
        if ".." in name or "/" in name or "\\" in name:
            return False
        return True


# -------------------------
# BOOT
# -------------------------
if __name__ == "__main__":
    jarvis = JarvisCore()

    print(f"JARVIS CORE v{__version__} iniciado")
    print("Skills carregadas:", jarvis.list_skills())

    # teste: listar notes do Memory via obsidian-brain
    if "obsidian-brain" in jarvis.skills:
        result = jarvis.run_skill("obsidian-brain", "list_notes", folder="Memory")
        print("\nMemory notes:", result)
    else:
        print("\n[AVISO] obsidian-brain nao encontrada em skills")

    # teste: verificar vault
    result = jarvis.run_skill("obsidian-brain", "verify_vault")
    print("\nverify_vault:", result)
