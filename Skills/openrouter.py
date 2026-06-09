from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class _OpenRouterSkill:
    def __init__(
        self,
        vault_path: str = ".",
        config_path: str = "Config/openrouter.json",
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.config_path = self.vault_path / config_path
        self.config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            self.config = {}
            return
        try:
            self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            self.config = {}

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def info(self) -> Dict[str, Any]:
        return {
            "name": "openrouter",
            "version": "0.1.0",
            "core_min_version": "3.3.0",
            "dependencies": [],
            "tags": ["llm", "openrouter", "provider", "chat"],
            "actions": [
                "set_api_key",
                "complete",
                "list_models",
                "status",
            ],
        }

    def _get_api_key(self) -> Optional[str]:
        return self.config.get("api_key")

    def _get_headers(self) -> Dict[str, str]:
        api_key = self._get_api_key()
        if not api_key:
            return {}
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _choose_model(self, preferred: Optional[str]) -> Tuple[str, Optional[str]]:
        primary = self.config.get("primary")
        fallback = self.config.get("fallback")
        model = preferred or primary or fallback
        if model == primary and fallback:
            return model, fallback
        return model, None

    def set_api_key(self, api_key: str) -> Dict[str, Any]:
        self.config["api_key"] = api_key
        self._save_config()
        return {"ok": True}

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"ok": False, "error": "openrouter api key missing"}
        chosen, fallback_model = self._choose_model(model)
        headers = self._get_headers()
        body: Dict[str, Any] = {
            "model": chosen,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if fallback_model and fallback_model != chosen:
                body["model"] = fallback_model
                try:
                    req = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=json.dumps(body).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                except Exception as exc2:
                    return {"ok": False, "error": str(exc2)}
            else:
                return {"ok": False, "error": str(exc)}
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = ""
        return {
            "ok": True,
            "model": chosen,
            "content": content,
            "raw": data,
        }

    def list_models(self) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"ok": False, "error": "openrouter api key missing"}
        headers = self._get_headers()
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "models": data}

    def status(self) -> Dict[str, Any]:
        api_key = self._get_api_key()
        return {
            "ok": True,
            "configured": bool(api_key),
            "primary": self.config.get("primary"),
            "fallback": self.config.get("fallback"),
        }

    def _execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {
            "set_api_key": self.set_api_key,
            "complete": self.complete,
            "list_models": self.list_models,
            "status": self.status,
        }
        fn = mapping.get(action)
        if not fn:
            return {"ok": False, "error": "unknown action: %s" % action}
        return fn(**payload)


_instance: Optional[_OpenRouterSkill] = None


def _get_instance() -> _OpenRouterSkill:
    global _instance
    if _instance is None:
        _instance = _OpenRouterSkill(vault_path=str(Path(__file__).resolve().parent.parent))
    return _instance


def info() -> Dict[str, Any]:
    return _get_instance().info()


def execute(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _get_instance()._execute(action, payload)


def set_api_key(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("set_api_key", payload)


def complete(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("complete", payload)


def list_models(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("list_models", payload)


def status(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("status", payload)
