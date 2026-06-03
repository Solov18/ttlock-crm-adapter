from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.errors import TTLockAPIError, error_hint


class TTLockClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, username: str, password_md5: str, lock_id: int, debug: bool = False):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password_md5 = password_md5
        self.lock_id = lock_id
        self.debug = debug
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None
        self.expires_at: float = 0

    @staticmethod
    def date_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {k: ("***" if k.lower() in {"accesstoken", "clientsecret", "password"} else v) for k, v in payload.items()}

    async def login(self) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret,
                    "username": self.username,
                    "password": self.password_md5,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        data = response.json()
        if "access_token" not in data:
            raise TTLockAPIError(f"TTLock auth failed: {data}", data)
        self.access_token = data["access_token"]
        self.refresh_token_value = data.get("refresh_token")
        self.expires_at = time.time() + int(data.get("expires_in", 0)) - 300

    async def refresh_token(self) -> None:
        if not self.refresh_token_value:
            await self.login()
            return
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token_value,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        data = response.json()
        if "access_token" not in data:
            await self.login()
            return
        self.access_token = data["access_token"]
        self.refresh_token_value = data.get("refresh_token", self.refresh_token_value)
        self.expires_at = time.time() + int(data.get("expires_in", 0)) - 300

    async def token(self) -> str:
        if not self.access_token:
            await self.login()
        elif time.time() >= self.expires_at:
            await self.refresh_token()
        assert self.access_token is not None
        return self.access_token

    async def _request(self, method: str, path: str, *, data: dict[str, Any] | None = None, params: dict[str, Any] | None = None, retry: bool = True) -> dict[str, Any]:
        token = await self.token()
        common = {"clientId": self.client_id, "accessToken": token, "date": self.date_ms()}
        if method.upper() == "GET":
            final_params = {**common, **(params or {})}
            final_data = None
        else:
            final_params = None
            final_data = {**common, **(data or {})}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, f"{self.base_url}{path}", params=final_params, data=final_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            payload = response.json()
        except Exception:
            payload = {"http_status": response.status_code, "raw_text": response.text}
        if self.debug:
            print("================================")
            print("TTLOCK PATH:", path)
            print("TTLOCK METHOD:", method)
            print("TTLOCK STATUS:", response.status_code)
            print("TTLOCK PARAMS:", self._safe_payload(final_params))
            print("TTLOCK DATA:", self._safe_payload(final_data))
            print("TTLOCK RESPONSE:", payload)
            print("================================")
        if isinstance(payload, dict) and payload.get("errcode") == 10004 and retry:
            await self.refresh_token()
            return await self._request(method, path, data=data, params=params, retry=False)
        errcode = payload.get("errcode") if isinstance(payload, dict) else None
        if errcode not in (None, 0):
            raise TTLockAPIError(f"TTLock error {errcode}: {error_hint(errcode)}", payload)
        return payload

    async def unlock(self) -> dict[str, Any]:
        last_error: TTLockAPIError | None = None
        for _ in range(3):
            try:
                return await self._request("POST", "/v3/lock/unlock", data={"lockId": self.lock_id})
            except TTLockAPIError as e:
                last_error = e
                if e.payload.get("errcode") in (-3003, -3037):
                    await asyncio.sleep(2)
                    continue
                raise
        assert last_error is not None
        raise last_error

    async def lock(self) -> dict[str, Any]:
        return await self._request("POST", "/v3/lock/lock", data={"lockId": self.lock_id})

    async def open_state(self) -> dict[str, Any]:
        return await self._request("GET", "/v3/lock/queryOpenState", params={"lockId": self.lock_id})

    async def battery(self) -> dict[str, Any]:
        return await self._request("GET", "/v3/lock/queryElectricQuantity", params={"lockId": self.lock_id})

    async def lock_detail(self) -> dict[str, Any]:
        return await self._request("GET", "/v3/lock/detail", params={"lockId": self.lock_id})

    async def gateway_list(self) -> dict[str, Any]:
        return await self._request("GET", "/v3/gateway/list", params={"pageNo": 1, "pageSize": 20, "orderBy": 1})

    async def add_passcode(self, code: str, name: str, *, permanent: bool = True, start_date: int | None = None, end_date: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"lockId": self.lock_id, "keyboardPwd": code, "keyboardPwdName": name, "addType": 2}
        if permanent:
            payload.update({"keyboardPwdType": 2, "startDate": 0, "endDate": 0})
        else:
            payload.update({"keyboardPwdType": 3, "startDate": start_date or self.date_ms(), "endDate": end_date or (self.date_ms() + 365 * 24 * 3600 * 1000)})
        return await self._request("POST", "/v3/keyboardPwd/add", data=payload)

    async def list_passcodes(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v3/lock/listKeyboardPwd",
            params={
                "lockId": self.lock_id,
                "pageNo": 1,
                "pageSize": 200,
                "orderBy": 1,
            },
        )

    async def list_cards(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v3/identityCard/list",
            params={
                "lockId": self.lock_id,
                "pageNo": 1,
                "pageSize": 200,
            },
        )

    async def delete_passcode(self, keyboard_pwd_id: int) -> dict[str, Any]:
        return await self._request("POST", "/v3/keyboardPwd/delete", data={"lockId": self.lock_id, "keyboardPwdId": keyboard_pwd_id, "deleteType": 2})

    async def add_card(self, card_number: str, name: str, *, permanent: bool = True, reversed_number: bool = True, start_date: int | None = None, end_date: int | None = None) -> dict[str, Any]:
        path = "/v3/identityCard/addForReversedCardNumber" if reversed_number else "/v3/identityCard/add"
        payload = {
            "lockId": self.lock_id,
            "cardNumber": card_number,
            "cardName": name,
            "addType": 2,
            "startDate": 0 if permanent else (start_date or self.date_ms()),
            "endDate": 0 if permanent else (end_date or (self.date_ms() + 365 * 24 * 3600 * 1000)),
        }
        return await self._request("POST", path, data=payload)

    async def delete_card(self, card_id: int) -> dict[str, Any]:
        return await self._request("POST", "/v3/identityCard/delete", data={"lockId": self.lock_id, "cardId": card_id, "deleteType": 2})

    async def lock_records(self, *, start_date: int | None = None, end_date: int | None = None, page_no: int = 1, page_size: int = 50) -> dict[str, Any]:
        params: dict[str, Any] = {"lockId": self.lock_id, "pageNo": page_no, "pageSize": page_size}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return await self._request("GET", "/v3/lockRecord/list", params=params)
