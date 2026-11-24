from fastapi import FastAPI

from .api import router

app = FastAPI(title="Restometra", version="0.1.0")
app.include_router(router)
