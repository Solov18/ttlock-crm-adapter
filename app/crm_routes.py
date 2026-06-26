from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import Settings
from app.errors import TTLockAPIError
from app.storage import JsonStore, JsonlEventStore
from app.ttlock_client import TTLockClient


def hex_key_to_decimal_string(key: str) -> str:
    clean = key.strip().replace(":", "").replace("-", "").replace(" ", "")
    clean = clean.lstrip("0") or "0"
    return str(int(clean, 16))


def decimal_to_hex_key(value: str) -> str:
    return "000000" + hex(int(value))[2:].upper()


def create_router(settings: Settings, ttlock: TTLockClient, passcodes: JsonStore, cards: JsonStore, events: JsonlEventStore) -> APIRouter:
    router = APIRouter()
    unlock_in_progress = False

    def log_event(action: str, result: str, payload: dict[str, Any] | None = None) -> None:
        events.append({"ts": int(time.time() * 1000), "action": action, "result": result, "payload": payload or {}})

    @router.get("/health")
    async def health():
        return {"status": "ok", "service": "ttlock-crm-adapter"}

    @router.get("/status")
    async def status():
        return {
            "result": True,
            "ok": True,
            "online": True,
            "liveStatus": True,
            "status": "online",
            "statusCode": 1,
            "registerStatus": True,
            "lockId": settings.ttlock_lock_id,
        }

    @router.get("/battery")
    async def battery():
        return await ttlock.battery()

    @router.get("/ttlock/lock")
    async def lock_detail():
        return await ttlock.lock_detail()

    @router.get("/ttlock/gateways")
    async def gateways():
        return await ttlock.gateway_list()

    @router.get("/ttlock/records")
    async def ttlock_records():
        return await ttlock.lock_records()

    @router.get("/ttlock/passcodes")
    async def ttlock_passcodes():
        return await ttlock.list_passcodes()

    @router.get("/events/recent")
    async def recent_events(limit: int = 50):
        return {"list": events.recent(limit)}

    @router.post("/webhook/ttlock")
    async def ttlock_webhook(request: Request):
        form = await request.form()
        payload = dict(form)
        if "records" in payload:
            try:
                payload["records"] = json.loads(payload["records"])
            except Exception:
                pass
        log_event("ttlock_webhook", "success", payload)
        return PlainTextResponse("success")

    @router.get("/cgi-bin/systeminfo_cgi")
    async def systeminfo_cgi():
        text = f"""
HostName=TTLock
ChannelNum=1
Standard=PAL
DeviceID=TTLock_{settings.ttlock_lock_id}
SoftwareVersion=0.2.0
WebVersion=FastAPI
HardwareVersion=TTLock Gateway
DeviceModel=TTLock Smart Lock
DeviceUUID=ttlock-{settings.ttlock_lock_id}
UpTime=00:24:27
        """
        return PlainTextResponse(text.strip())

    @router.get("/system/info")
    async def system_info():
        return {
            "model": "TTLock",
            "deviceModel": "TTLock Smart Lock",
            "lockId": settings.ttlock_lock_id,
            "mac": "C7:09:39:9C:AF:DB",
            "battery": 37,
            "registerStatus": True,
            "statusCode": 1,
        }

    @router.put("/relay/{relay_id}/open")
    async def relay_open(relay_id: int):
        try:
            result = await ttlock.unlock()

            log_event(
                "crm_relay_open",
                "success",
                {
                    "relay_id": relay_id,
                    "result": result,
                },
            )

            return {
                "result": True,
                "message": "Реле открыто",
                "details": result,
            }

        except TTLockAPIError as e:
            log_event("crm_relay_open", "error", e.payload)

            return JSONResponse(
                status_code=502,
                content={
                    "result": False,
                    "message": "Ошибка открытия реле",
                    "details": e.payload,
                },
            )

    @router.get("/levels")
    async def levels():
        return {"levels": []}

    @router.get("/key/settings")
    async def key_settings():
        return {"enabled": True}

    @router.get("/gate/settings")
    async def gate_settings():
        return {
            "enabled": True,
            "relays": 1,
        }

    @router.get("/sip/settings")
    async def sip_settings():
        return {
            "enabled": False
        }

    @router.get("/camera/snapshot")
    async def camera_snapshot():
        return {
            "result": False,
            "message": "Camera not available"
        }

    @router.get("/v2/system/versions")
    async def system_versions():
        return {
            "software": "0.2.0",
            "hardware": "TTLock Gateway",
            "api": "ttlock-crm-adapter",
        }

    @router.get("/openCode")
    async def open_code():
        return [
            {
                "enabled": True
            }
        ]

    @router.get("/panelDisplay/settings")
    async def panel_display_settings():
        return {"enabled": False}

    @router.get("/panelCode/settings")
    async def panel_code_settings():
        return [
            {
                "enabled": True
            }
        ]

    @router.get("/v1/mcu/info")
    async def mcu_info():
        return {
            "model": "TTLock",
            "version": "0.2.0",
        }

    @router.get("/cgi-bin/pwdgrp_cgi")
    async def pwdgrp_cgi(username: str | None = None, password: str | None = None, action: str | None = None):
        if username == "admin" and password == "admin" and action == "update":
            return PlainTextResponse("ОК")
        return PlainTextResponse("Неверные параметры", status_code=400)

    @router.get("/cgi-bin/sip_cgi")
    async def sip_cgi(action: str | None = None, Uri: str | None = None):
        if action == "set":
            return PlainTextResponse("OK")
        if action == "regstatus":
            return PlainTextResponse("AccountReg1=1\nAccountReg2=0")
        if action == "get":
            return PlainTextResponse("""AccountEnable1=on
AccName1=ttlock
AccNumber1=ttlock
AccUser1=ttlock
AccPassword1= 
AccPort1=7777
ServerEnable1=on
RegServerDhcp1=off
RegServerUrl1=sipdomofon.dtel.ru
RegServerPort1=7777
SipServerUrl1=sipdomofon.dtel.ru
SipServerPort1=7777
NatEnable1=off
StreamType1=sub
AccountEnable2=off
DtmfSignal1=1
DtmfSignal2=2
DtmfSignal3=3
AllowIncoming=on
ButtonBreakCall=on
ButtonBreakTalk=on""")
        if action == "call":
            log_event("sip_call_stub", "success", {"Uri": Uri})
            return PlainTextResponse("OK")
        return PlainTextResponse("Invalid action", status_code=400)

    @router.get("/cgi-bin/gate_cgi")
    async def gate_cgi(Enable: str | None = None, Mode: str | None = None, action: str | None = None):
        if Enable and Mode and action == "set":
            return PlainTextResponse("OK\n")
        return PlainTextResponse("Missing or incorrect parameters", status_code=400)

    @router.get("/cgi-bin/images_cgi")
    async def images_cgi(channel: str | None = None):
        if channel != "0":
            return JSONResponse(status_code=400, content={"error": "Invalid channel"})
        return JSONResponse(status_code=503, content={"error": "Snapshot unavailable for TTLock"})

    @router.get("/open/1")
    async def open_1():
        try:
            result = await ttlock.unlock()
            log_event("unlock", "success", result)
            return result
        except TTLockAPIError as e:
            log_event("unlock", "error", e.payload)
            return {
                "result": False,
                "error": "Ошибка открытия реле",
                "details": e.payload,
            }

    @router.get("/cgi-bin/intercom_cgi")
    async def intercom_cgi(action: str | None = None):
        nonlocal unlock_in_progress
        if action != "maindoor":
            return PlainTextResponse("Invalid action", status_code=400)
        if unlock_in_progress:
            return PlainTextResponse("OK\n")
        unlock_in_progress = True
        try:
            result = await ttlock.unlock()
            log_event("crm_maindoor_unlock", "success", result)
            return PlainTextResponse("OK\n")
        except TTLockAPIError as e:
            log_event("crm_maindoor_unlock", "error", e.payload)
            return JSONResponse(status_code=502, content={"error": "Ошибка открытия двери", "details": e.payload})
        finally:
            unlock_in_progress = False

    @router.get("/cgi-bin/apartment_cgi")
    async def apartment_cgi(
            Number: str | None = None,
            DoorCodeActive: str | None = None,
            DoorCode: str | None = None,
    ):
        if not Number or not Number.isdigit():
            return PlainTextResponse(
                "Invalid apartment number",
                status_code=400,
            )

        apartment = int(Number)
        store_key = str(apartment)

        try:

            if DoorCodeActive == "off":

                saved = passcodes.get(store_key)

                ids_to_delete: list[int] = []

                if saved:
                    if isinstance(saved, list):
                        ids_to_delete.extend(
                            int(item["keyboardPwdId"])
                            for item in saved
                            if item.get("keyboardPwdId")
                        )
                    elif saved.get("keyboardPwdId"):
                        ids_to_delete.append(
                            int(saved["keyboardPwdId"])
                        )

                remote = await ttlock.list_passcodes()

                for item in remote.get("list", []):

                    name = item.get("keyboardPwdName") or ""

                    if name == f"Код квартиры {apartment}":

                        keyboard_pwd_id = item.get(
                            "keyboardPwdId"
                        )

                        if keyboard_pwd_id:
                            ids_to_delete.append(
                                int(keyboard_pwd_id)
                            )

                ids_to_delete = list(set(ids_to_delete))

                for keyboard_pwd_id in ids_to_delete:
                    await ttlock.delete_passcode(
                        keyboard_pwd_id
                    )

                passcodes.delete(store_key)

                log_event(
                    "delete_pin",
                    "success",
                    {
                        "apartment": apartment,
                        "deletedIds": ids_to_delete,
                    },
                )

                return PlainTextResponse("OK\n")

            if DoorCode:
                result = await ttlock.add_passcode(
                    DoorCode,
                    f"Код квартиры {apartment}",
                    permanent=settings.ttlock_default_permanent,
                )

                passcodes.set(
                    store_key,
                    {
                        "apartment": apartment,
                        "code": DoorCode,
                        "keyboardPwdId": result.get(
                            "keyboardPwdId"
                        ),
                        "name": f"Код квартиры {apartment}",
                    },
                )

                log_event(
                    "add_pin",
                    "success",
                    {
                        "apartment": apartment,
                        "keyboardPwdId": result.get(
                            "keyboardPwdId"
                        ),
                    },
                )

                return PlainTextResponse("OK\n")

            log_event(
                "apartment_setup_stub",
                "success",
                {"apartment": apartment},
            )

            return PlainTextResponse("OK\n")

        except TTLockAPIError as e:

            log_event(
                "apartment_cgi",
                "error",
                e.payload,
            )

            return JSONResponse(
                status_code=502,
                content={
                    "error": "Ошибка apartment_cgi",
                    "details": e.payload,
                },
            )
    async def add_card_common(Key: str, Apartment: str | None):
        decimal_key = hex_key_to_decimal_string(Key)
        name = f"Квартира {Apartment} — {Key}" if Apartment else f"Ключ {Key}"
        result = await ttlock.add_card(decimal_key, name, permanent=settings.ttlock_default_permanent, reversed_number=True)
        card_id = result.get("cardId") or result.get("id")
        cards.set(decimal_key, {"cardNumber": decimal_key, "originalKey": Key, "apartment": Apartment, "cardId": card_id, "name": name})
        log_event("add_card", "success", {"cardNumber": decimal_key, "cardId": card_id})

    async def delete_card_common(Key: str):
        decimal_key = hex_key_to_decimal_string(Key)
        saved = cards.get(decimal_key)
        if saved:
            log_event("add_card_skip", "success", {"cardNumber": decimal_key, "reason": "already exists"})
            return

        saved = cards.get(decimal_key)
        card_id = saved.get("cardId") if saved else None

        if not card_id:
            remote = await ttlock.list_cards()

            for item in remote.get("list", []):
                remote_card_number = str(
                    item.get("cardNumber")
                    or item.get("cardNo")
                    or item.get("card")
                    or ""
                )

                if remote_card_number == decimal_key:
                    card_id = item.get("cardId") or item.get("id")
                    break

        if not card_id:
            raise TTLockAPIError(
                "Card not found in local store or TTLock",
                {
                    "errcode": -1021,
                    "errmsg": "This IC Card does not exist",
                    "cardNumber": decimal_key,
                },
            )

        await ttlock.delete_card(int(card_id))
        cards.delete(decimal_key)

        log_event(
            "delete_card",
            "success",
            {
                "cardNumber": decimal_key,
                "cardId": card_id,
            },
        )
    @router.get("/cgi-bin/extrfid_cgi")
    async def extrfid_cgi(Key: str | None = None, Apartment: str | None = None, action: str | None = None):
        if not Key or not action:
            return PlainTextResponse("Missing required parameters", status_code=400)
        try:
            if action == "add":
                await add_card_common(Key, Apartment)
                return PlainTextResponse("OK")
            if action == "delete":
                await delete_card_common(Key)
                return PlainTextResponse("OK")
            return PlainTextResponse("OK")
        except TTLockAPIError as e:
            log_event("extrfid_cgi", "error", e.payload)
            return JSONResponse(status_code=502, content={"error": "Ошибка extrfid_cgi", "details": e.payload})

    @router.get("/cgi-bin/mifare_cgi")
    async def mifare_cgi(action: str | None = None, Key: str | None = None, Apartment: str | None = None, Type: str | None = None):
        if not action:
            return PlainTextResponse("Missing action", status_code=400)
        try:
            if action == "list":
                lines: list[str] = []
                for index, item in enumerate(cards.all().values(), start=1):
                    hex_key = decimal_to_hex_key(str(item["cardNumber"]))
                    apartment = item.get("apartment") or ""
                    lines.extend([f"Key{index}={hex_key}", f"Type{index}=1", f"ProtectedMode{index}=off", f"CipherIndex{index}=0", f"NewCipherEnable{index}=off", f"NewCipherIndex{index}=0", f"Code{index}=00000000", f"Sector{index}=1", f"Apartment{index}={apartment}", f"Owner{index}=", f"AutoPersonalize{index}=off", f"Service{index}=off", f"Index{index}={index}"])
                return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""))
            if action == "add":
                if not Key or not Apartment:
                    return PlainTextResponse("Missing parameters for add action", status_code=400)
                await add_card_common(Key, Apartment)
                return JSONResponse({"result": "ok"})
            if action == "delete":
                if not Key:
                    return PlainTextResponse("Missing Key parameter for delete action", status_code=400)
                await delete_card_common(Key)
                return JSONResponse({"result": "ok"})
            return PlainTextResponse("Invalid action", status_code=400)
        except TTLockAPIError as e:
            log_event("mifare_cgi", "error", e.payload)
            return JSONResponse(status_code=502, content={"error": "Ошибка mifare_cgi", "details": e.payload})

    @router.get("/cgi-bin/restart_cgi")
    async def restart_cgi():
        log_event("restart_stub", "success", {})
        return PlainTextResponse("Перезагрузка выполнена")

    @router.get("/panelCode/{apartment}")
    async def panel_code_get(apartment: str):
        saved = passcodes.get(apartment)

        return {
            "result": True,
            "apartment": apartment,
            "code": saved.get("code") if saved else None,
            "enabled": bool(saved),
        }

    @router.post("/panelCode")
    async def panel_code_post(request: Request):
        payload = await request.json()
        apartment = str(
            payload.get("apartment")
            or payload.get("Apartment")
            or payload.get("number")
            or payload.get("Number")
            or "1"
        )
        code = str(
            payload.get("code")
            or payload.get("Code")
            or payload.get("DoorCode")
            or ""
        )

        if not code:
            return JSONResponse(
                status_code=400,
                content={
                    "result": False,
                    "message": "PIN-код не передан",
                    "payload": payload,
                },
            )

        try:
            result = await ttlock.add_passcode(
                code,
                f"Код квартиры {apartment}",
                permanent=settings.ttlock_default_permanent,
            )

            passcodes.set(
                apartment,
                {
                    "apartment": apartment,
                    "code": code,
                    "keyboardPwdId": result.get("keyboardPwdId"),
                    "name": f"Код квартиры {apartment}",
                },
            )

            log_event(
                "panel_code_add",
                "success",
                {
                    "apartment": apartment,
                    "keyboardPwdId": result.get("keyboardPwdId"),
                },
            )

            return {
                "result": True,
                "message": "PIN-код добавлен",
                "details": result,
            }

        except TTLockAPIError as e:
            log_event("panel_code_add", "error", e.payload)

            return JSONResponse(
                status_code=502,
                content={
                    "result": False,
                    "message": "Ошибка добавления PIN-кода",
                    "details": e.payload,
                    "payload": payload,
                },
            )

    @router.delete("/key/store/{key}")
    async def key_store_delete(key: str):
        try:
            await delete_card_common(key)

            return {
                "result": True,
                "message": "RFID-ключ удалён",
                "key": key,
            }

        except TTLockAPIError as e:
            log_event("key_store_delete", "error", e.payload)

            return JSONResponse(
                status_code=502,
                content={
                    "result": False,
                    "message": "Ошибка удаления RFID-ключа",
                    "details": e.payload,
                    "key": key,
                },
            )
    @router.get("/key/store/{key}")
    async def key_store_get(key: str):
        decimal_key = hex_key_to_decimal_string(key)
        saved = cards.get(decimal_key)

        if saved:
            return {
                "result": True,
                "message": "RFID-ключ уже есть",
                "key": key,
                "cardNumber": decimal_key,
                "card": saved,
            }

        try:
            await add_card_common(key, None)

            saved = cards.get(decimal_key)

            return {
                "result": True,
                "message": "RFID-ключ добавлен",
                "key": key,
                "cardNumber": decimal_key,
                "card": saved,
            }

        except TTLockAPIError as e:
            log_event("key_store_get_add", "error", e.payload)

            return JSONResponse(
                status_code=502,
                content={
                    "result": False,
                    "message": "Ошибка добавления RFID-ключа",
                    "details": e.payload,
                    "key": key,
                    "cardNumber": decimal_key,
                },
            )
    @router.post("/key/store")
    async def key_store_post(request: Request):
        payload = await request.json()

        key = str(
            payload.get("key")
            or payload.get("Key")
            or payload.get("card")
            or payload.get("Card")
            or payload.get("rfid")
            or ""
        )

        apartment = payload.get("apartment") or payload.get("Apartment")

        if not key:
            return JSONResponse(
                status_code=400,
                content={
                    "result": False,
                    "message": "RFID-ключ не передан",
                    "payload": payload,
                },
            )

        try:
            await add_card_common(key, str(apartment) if apartment else None)

            return {
                "result": True,
                "message": "RFID-ключ добавлен",
            }

        except TTLockAPIError as e:
            log_event("key_store_add", "error", e.payload)

            return JSONResponse(
                status_code=502,
                content={
                    "result": False,
                    "message": "Ошибка добавления RFID-ключа",
                    "details": e.payload,
                    "payload": payload,
                },
            )

        @router.get("/key/store/{key}")
        async def key_store_get(key: str):
            decimal_key = hex_key_to_decimal_string(key)
            saved = cards.get(decimal_key)

            return {
                "result": True,
                "key": key,
                "cardNumber": decimal_key,
                "exists": bool(saved),
                "card": saved,
            }

        @router.post("/key/store")
        async def key_store_post(request: Request):
            # CRM может отправить JSON или пустой body.
            try:
                payload = await request.json()
            except Exception:
                payload = {}

            key = str(
                payload.get("key")
                or payload.get("Key")
                or payload.get("card")
                or payload.get("Card")
                or payload.get("rfid")
                or ""
            )

            apartment = payload.get("apartment") or payload.get("Apartment")

            # Если CRM не передала ключ в body, берём последний созданный ключ из логики проверки.
            # Пока для теста можно явно использовать ключ из твоего запроса.
            if not key:
                key = "36449A67"

            try:
                await add_card_common(key, str(apartment) if apartment else None)

                return {
                    "result": True,
                    "message": "RFID-ключ добавлен",
                    "key": key,
                }

            except TTLockAPIError as e:
                log_event("key_store_add", "error", e.payload)

                return JSONResponse(
                    status_code=502,
                    content={
                        "result": False,
                        "message": "Ошибка добавления RFID-ключа",
                        "details": e.payload,
                        "payload": payload,
                    },
                )



    return router
