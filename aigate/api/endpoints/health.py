from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    runner = getattr(request.app.state, "shield_runner", None)
    return JSONResponse({
        "status": "ok",
        "shields_loaded": len(runner.shields) if runner else 0,
    })
