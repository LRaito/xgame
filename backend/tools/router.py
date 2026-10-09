from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.deps import CurrentUser
from backend.http import json_ok
from backend.tools.registry import list_tools

router = APIRouter(tags=["tools"])


@router.get("/health")
def health():
    return PlainTextResponse("ok", status_code=200)


@router.get("/api/tools")
def tools(_user: CurrentUser):
    return json_ok(
        [
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "path": spec.path,
            }
            for spec in list_tools()
        ]
    )
