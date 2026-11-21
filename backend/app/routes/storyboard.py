from fastapi import APIRouter, Depends, Request

from ..config import Settings, get_settings
from ..services.storyboard import create_storyboard
from ..services.storyboard_input import read_storyboard_input

router = APIRouter(prefix="/api")


@router.post("/storyboard")
async def storyboard(request: Request, settings: Settings = Depends(get_settings)):
    return await create_storyboard(settings, **await read_storyboard_input(request, settings))
