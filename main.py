from fastapi import FastAPI
from routers import auth, model
import uvicorn

app = FastAPI()
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(model.router)

