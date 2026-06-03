# TTLock CRM Adapter

Python/FastAPI адаптер, который эмулирует CGI-интерфейсы панели для CRM dtel
и переводит команды в TTLock Cloud API.

## Что умеет

- Открыть замок:
  - `/cgi-bin/intercom_cgi?action=maindoor`
- Добавить/удалить PIN-код:
  - `/cgi-bin/apartment_cgi?Number=101&DoorCode=123456`
  - `/cgi-bin/apartment_cgi?Number=101&DoorCodeActive=off`
- Добавить/удалить RFID/IC card:
  - `/cgi-bin/mifare_cgi?action=add&Key=000000A1B2C3&Apartment=101&Type=1`
  - `/cgi-bin/mifare_cgi?action=delete&Key=000000A1B2C3`
  - `/cgi-bin/extrfid_cgi?action=add&Key=000000A1B2C3&Apartment=101`
  - `/cgi-bin/extrfid_cgi?action=delete&Key=000000A1B2C3&Apartment=101`
- Получить список карт:
  - `/cgi-bin/mifare_cgi?action=list`
- Статус:
  - `/status`
- Батарея:
  - `/battery`
- События:
  - `/events/recent`
  - `/webhook/ttlock`

## Быстрый запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate  # Linux
# .venv\Scripts\activate  # Windows

pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Docker

```bash
cp .env.example .env
docker compose up -d --build
```

## Важно по TTLock

Удалённое открытие, добавление PIN и RFID работают только если замок WiFi
или подключён через Gateway. Для открытия в TTLock APP должна быть включена
опция Remote Unlock.
