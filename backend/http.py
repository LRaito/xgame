from datetime import datetime

from fastapi.responses import JSONResponse


def json_ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=status)


def json_err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
