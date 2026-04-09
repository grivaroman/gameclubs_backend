from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import models
from web import router as web_router
from api import router as api_router

app = FastAPI(title="CyberBooking System")

@app.on_event("startup")
async def startup():
    async with models.engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/login")

app.include_router(web_router)
app.include_router(api_router)