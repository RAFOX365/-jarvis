import importlib.util
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

VAULT = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
__version__ = "3.2.0"


# -------------------------
# EVENT SYSTEM
# -------------------------
class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event: str, callback: Callable):
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable):
        if event in self._listeners:
            self._listeners[event] = [cb for cb in self._listeners[event] if cb != callback]

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None):
        payload = payload or {}
        payload.setdefault("timestamp", datetime.now().isoformat())
        payload.setdefault("event", event)
        payload.setdefault("version", __version__)
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:
                pass
        return payload


# -------------------------
# UTIL
# -------------------------
def _now_iso() -> str:
    return datetime.now().isoformat()


def _fail(error: str) -> Dict[str, Any]:
    return {"ok": False, "error": error}


def _ok(data: Any = None) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def _safe_name(name: str) -> bool:
    if not name:
        return False
    # bloqueia apenas path traversal e chars perigosos
    if ".." in name or name.startswith("/") or name.startswith("\\"):
        return False
    # aceita alfanumerico, hifen, underline
    if not all(c.isalnum() or c in "-_" for c in name):
        return False
    return True


# -------------------------
# CORE ENGINE
# -------------------------
class JarvisCoreV32:

    def __init__(self, vault_path: str = VAULT):
        self.vault = Path(vault_path).resolve()
        self.skills_path = self.vault / "Skills"
        self.logs_path = self.vault / "Logs" / "core.log.jsonl"
        self.events = EventEmitter()
        self.skills: Dict[str, Any] = {}
        self.skill_meta: Dict[str, Dict[str, Any]] = {}

        self._ensure_structure()
        self._load_safe_logger()
        self._register_default_hooks()
        self.load_skills()

        self.events.emit("CORE_INIT", {
            "vault": str(self.vault),
            "version": __version__
        })

    # -------------------------
    # ESTRUTURA
    # -------------------------
    def _ensure_structure(self):
        (self.vault / "Skills").mkdir(parents=True, exist_ok=True)
        (self.vault / "Logs").mkdir(parents=True, exist_ok=True)

    # -------------------------
    # SAFE LOGGER (carregado do vault)
    # -------------------------
    def _load_safe_logger(self):
        candidate = self.skills_path / "safe-logger.py"
        if not candidate.exists():
            raise FileNotFoundError(f"SafeLogger não encontrado em {candidate}")

        spec = importlib.util.spec_from_file_location("safe_logger", candidate)
        if spec is None or spec.loader is None:
            raise ImportError("spec inválido para safe-logger")

        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.logger = mod.SafeLogger(path=self.logs_path)
        self.skills["safe-logger"] = mod

    # -------------------------
    # HOOKS DEFAULT
    # -------------------------
    def _register_default_hooks(self):
        self.events.on("SKILL_LOADED", lambda p: self.logger.write(
            "SKILL_LOADED", {"skill": p.get("skill")}, level="INFO"
        ))
        self.events.on("SKILL_LOAD_FAIL", lambda p: self.logger.write(
            "SKILL_LOAD_FAIL", {"skill": p.get("skill"), "error": p.get("error")}, level="ERROR"
        ))
        self.events.on("SKILL_EXEC", lambda p: self.logger.write(
            "SKILL_EXEC", {
                "skill": p.get("skill"),
                "action": p.get("action"),
                "elapsed_ms": p.get("elapsed_ms")
            }, level="INFO"
        ))
        self.events.on("SKILL_ERROR", lambda p: self.logger.write(
            "SKILL_ERROR", {
                "skill": p.get("skill"),
                "action": p.get("action"),
                "error": p.get("error")
            }, level="ERROR"
        ))

    # -------------------------
    # LOAD SKILLS
    # -------------------------
    def load_skills(self, reload: bool = False):
        if not self.skills_path.exists():
            return

        # se for reload, limpa skills antigas (menos safe-logger)
        if reload:
            to_remove = [k for k in self.skills if k != "safe-logger"]
            for k in to_remove:
                del self.skills[k]
                self.skill_meta.pop(k, None)
            # limpa cache do importlib
            for key in list(sys.modules.keys()):
                if key.startswith("Skills.") or key.startswith("jarvis_skill_"):
                    del sys.modules[key]

        for file in sorted(self.skills_path.glob("*.py")):
            name = file.stem
            if not _safe_name(name):
                continue
            if name in self.skills and not reload:
                continue

            try:
                module_name = f"Skills.{name}"
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec is None or spec.loader is None:
                    raise ImportError("spec inválido")

                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                self.skills[name] = module
                meta = {
                    "name": name,
                    "file": str(file),
                    "module": module_name
                }
                if hasattr(module, "info") and callable(module.info):
                    try:
                        info_data = module.info()
                        if isinstance(info_data, dict):
                            meta.update(info_data)
                    except Exception:
                        pass
                self.skill_meta[name] = meta

                self.events.emit("SKILL_LOADED", {
                    "skill": name,
                    "meta": meta
                })

            except Exception as e:
                self.events.emit("SKILL_LOAD_FAIL", {
                    "skill": name,
                    "error": str(e)
                })

    # -------------------------
    # EXECUTION ENGINE
    # -------------------------
    def run_skill(
        self,
        skill_name: str,
        action: str,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()

        if not _safe_name(skill_name) or not _safe_name(action):
            return _fail("invalid_name")

        if skill_name not in self.skills:
            return _fail("skill_not_found")

        skill = self.skills[skill_name]
        if not hasattr(skill, action):
            return {
                "error": "action_not_found",
                "available_actions": [
                    m for m in dir(skill)
                    if not m.startswith("_") and callable(getattr(skill, m))
                ]
            }

        try:
            method = getattr(skill, action)
            result = method(**kwargs)

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            event_payload = {
                "skill": skill_name,
                "action": action,
                "elapsed_ms": elapsed_ms,
                "result": str(result)[:500]
            }
            self.events.emit("SKILL_EXEC", event_payload)

            return {
                "ok": True,
                "event_id": event_payload.get("timestamp"),
                "execution_time_ms": elapsed_ms,
                "result": result
            }

        except Exception as e:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            event_payload = {
                "skill": skill_name,
                "action": action,
                "error": str(e),
                "elapsed_ms": elapsed_ms
            }
            self.events.emit("SKILL_ERROR", event_payload)

            return {
                "ok": False,
                "event_id": event_payload.get("timestamp"),
                "execution_time_ms": elapsed_ms,
                "error": str(e)
            }

    # -------------------------
    # INSPECTION
    # -------------------------
    def list_skills(self) -> List[str]:
        return sorted(self.skills.keys())

    def list_actions(self, skill_name: str) -> List[str]:
        if skill_name not in self.skills:
            return []
        skill = self.skills[skill_name]
        return [
            m for m in dir(skill)
            if not m.startswith("_") and callable(getattr(skill, m))
        ]

    def get_skill_meta(self, skill_name: str) -> Dict[str, Any]:
        return self.skill_meta.get(skill_name, {})

    def get_event_stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        listeners: Dict[str, int] = {}
        for event, cbs in self.events._listeners.items():
            counts[event] = len(cbs)
            listeners[event] = len(cbs)
        return {
            "total_events": len(self.events._listeners),
            "listeners": listeners,
            "skills_loaded": len(self.skills),
            "skills": list(self.skills.keys())
        }

    # -------------------------
    # SHUTDOWN / CONTEXT MANAGER
    # -------------------------
    def close(self):
        self.events.emit("CORE_SHUTDOWN", {
            "vault": str(self.vault),
            "skills_loaded": len(self.skills)
        })

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# -------------------------
# BOOT
# -------------------------
if __name__ == "__main__":
    with JarvisCoreV32() as core:
        print(f"JARVIS CORE v{__version__}")
        print("Skills:", core.list_skills())
        print("Event stats:", core.get_event_stats())
        if "obsidian-brain" in core.skills:
            print("obsidian actions:", core.list_actions("obsidian-brain"))
        if "git-ops" in core.skills:
            print("git actions:", core.list_actions("git-ops"))
