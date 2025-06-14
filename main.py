from fastapi import FastAPI
from routers import auth, model
# import uvicorn

app = FastAPI()
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(model.router)


# if __name__ == "__main__":
#     uvicorn.run(
#         "main:app",
#         host="127.0.0.1",
#         port=8000,
#         reload=True
#     )

