import uvicorn
from fastapi import FastAPI, Request

from app.config import get_settings
from app.crm_routes import create_router
from app.storage import JsonStore, JsonlEventStore
from app.ttlock_client import TTLockClient

settings = get_settings()

ttlock = TTLockClient(
    base_url=settings.ttlock_base_url,
    client_id=settings.ttlock_client_id,
    client_secret=settings.ttlock_client_secret,
    username=settings.ttlock_username,
    password_md5=settings.ttlock_password_md5,
    lock_id=settings.ttlock_lock_id,
    debug=settings.debug_ttlock,
)

passcodes = JsonStore(f"{settings.data_dir}/passcodes.json")
cards = JsonStore(f"{settings.data_dir}/cards.json")
events = JsonlEventStore(f"{settings.data_dir}/events.jsonl")

app = FastAPI(title="TTLock CRM Adapter", version="0.2.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Запрос: {request.method} {request.url.path}?{request.url.query}")
    response = await call_next(request)
    print(f"Ответ: {response.status_code}")
    return response


app.include_router(create_router(settings, ttlock, passcodes, cards, events))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)
