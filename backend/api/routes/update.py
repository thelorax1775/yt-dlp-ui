from fastapi import APIRouter, Header, HTTPException

from services import updater

router = APIRouter()


@router.get("/update/check")
async def update_check():
    return await updater.check()


@router.get("/update/status")
async def update_status():
    return {"job": updater.get_job()}


@router.post("/update", status_code=202)
async def update_start(x_admin_token: str | None = Header(default=None)):
    # No login in this app: an admin token from the environment gates the
    # update. The custom header also makes a browser preflight other sites fail.
    if not updater.admin_token():
        raise HTTPException(403, "Updating is disabled: set UPDATE_ADMIN_TOKEN on the backend.")
    if not updater.check_admin(x_admin_token):
        raise HTTPException(403, "Wrong or missing admin token.")
    try:
        return {"job": await updater.start_update()}
    except RuntimeError as e:
        reason = str(e)
        if reason == "not_configured":
            raise HTTPException(409, "UPDATE_MODE is not set (docker or systemd).")
        if reason == "busy":
            raise HTTPException(409, "An update is already running.")
        raise HTTPException(409, "Already up to date.")
    except ConnectionError as e:
        raise HTTPException(502, str(e))
