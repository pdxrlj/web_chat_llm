from fastapi import FastAPI
from app.http.router import register_handlers, lifespan, register_routes

app = FastAPI(title="NL-Chat", lifespan=lifespan)

register_handlers(app)
register_routes(app, "app.http.handlers")
