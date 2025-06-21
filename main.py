from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from src.database import asession_manager
from src.apps.alerts.router import router as alerts_router
from src.apps.areas_trans_meters.router import router as areas_trans_meters_router
from src.apps.data.router import router as data_router
from src.apps.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asession_manager.init_db()
    yield
    await asession_manager.close()


app = FastAPI(
    title="Enerlytics",
    version="0.1.0",
    description="Electricity distribution analysis API.",
    lifespan=lifespan,
)


@app.get(
    "/",
    description="Root endpoint",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
)
async def root():
    return {"message": "Welcome to Enerlytics!"}


app.include_router(users_router)
app.include_router(alerts_router)
app.include_router(areas_trans_meters_router)
app.include_router(data_router)
