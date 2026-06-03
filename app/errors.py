class TTLockAPIError(RuntimeError):
    def __init__(self, message: str, payload: dict | None = None):
        super().__init__(message)
        self.payload = payload or {}


TTLOCK_ERROR_HINTS = {
    10000: "client_id does not exist",
    10001: "invalid client_id or client_secret",
    10003: "token does not exist",
    10004: "token is invalid or revoked",
    10007: "invalid account or invalid password",
    20002: "not lock admin",
    80000: "date must be current time, within 5 minutes",
    -3: "invalid parameter",
    -1003: "lock does not exist",
    -2012: "lock is not connected to any gateway",
    -3002: "gateway is offline",
    -3003: "gateway is busy",
    -3035: "wifi lock is in power saving mode",
    -3036: "lock is offline",
    -3037: "lock is busy",
    -4043: "function not supported; enable Remote Unlock in TTLock APP",
    -3006: "invalid passcode length, should be 6-9 digits",
    -3007: "same passcode already exists",
    -3009: "no space for customized passcodes",
    -1021: "IC card does not exist",
}


def error_hint(errcode: int | None) -> str:
    if errcode is None:
        return "unknown error"
    return TTLOCK_ERROR_HINTS.get(errcode, "unknown TTLock error")
