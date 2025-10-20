# jobs/constants.py
STATE_MAP = {
    "PENDING":  "PENDING",
    "RECEIVED": "RECEIVED",
    "SENT":     "SENT",
    "STARTED":  "STARTED",
    "PROGRESS": "PROGRESS",   # custom while updating meta
    "RETRY":    "RETRY",
    "SUCCESS":  "SUCCESS",
    "FAILURE":  "FAILURE",
    "REVOKED":  "REVOKED",
}
ALL_STATES = tuple(STATE_MAP.values())
