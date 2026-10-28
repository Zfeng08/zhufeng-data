"""公共工具：带 UA 的 HTTP 请求与北京时间。"""
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def http_get(url, timeout=20, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(2)
    raise last


def now_cst():
    return datetime.now(CST).isoformat(timespec="seconds")
