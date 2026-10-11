from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

from app.api.routes import auth, chat, health, portal, records, workbooks
from app.api.routes import actions, voice

app = FastAPI(title="Sheet2Portal API")

app.add_middleware(
    CORSMiddleware,
    # Explicit origins (never "*") because the session cookie is sent
    # with credentials.
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workbooks.router)
app.include_router(portal.router)
app.include_router(records.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(actions.router)
