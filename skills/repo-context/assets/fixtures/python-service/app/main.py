from fastapi import FastAPI

from app.router import router

app = FastAPI()
app.include_router(router)


def create_app() -> FastAPI:
    return app
