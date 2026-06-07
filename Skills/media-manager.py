from typing import Any, Dict


def info() -> Dict[str, Any]:
    return {
        "name": "Gerenciador de Mídia",
        "version": "1.0.0",
        "core_min_version": "3.3.0",
        "dependencies": [],
        "tags": ["media", "automation"],
        "actions": ["publicar_feed", "deletar_post"]
    }


def execute(action: str, context: Dict[str, Any]) -> bool:
    if action == "publicar_feed":
        return _processar_publicacao(context)
    if action == "deletar_post":
        return _processar_remocao(context)
    raise ValueError(f"Ação desconhecida: {action}")


def _processar_publicacao(ctx: Dict[str, Any]) -> bool:
    print(f"[media] post -> {ctx.get('legenda', 'Sem legenda')}")
    return True


def _processar_remocao(ctx: Dict[str, Any]) -> bool:
    print(f"[media] delete post_id={ctx.get('post_id')}")
    return True
