from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from typing import Any
from urllib.parse import urlencode

BASE = "https://editor-api-sg.capcutapi.com"
DEFAULT_DEVICE = {
    "aid": "359289", "app_name": "CapCut", "appvr": "8.7.0",
    "version_name": "8.7.0", "version_code": "8.7.0",
    "channel": "capcutpc_google", "device_platform": "mac",
    "device_type": "MacBookPro17,1", "device_brand": "MacBookPro17,1",
    "os_version": "15.7.4", "region": "VN", "loc": "VN",
    "lan": "vi-VN", "pf": "3",
}
PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmTd34Lw4b7IuldSXh/zY
CMla+ITdGG5TeWz6ad+OySd4r+IrY45AoqrYUxhQ2dl+7z+i7r/5vEa8rr39BYfB
8AGMQLmZA8HmgpWBsqrn/V6daUALkKnkLb70Fn32CJigIuGXAYqxUdGuI340aC+0
v5Es3puJsHyzf01/AelE4Cdc6bZhQrASJLBh8R3BQToYClmDVSDUQk28o8sl/guA
Z4n303Vj+6Siv1HayPCdV6kpVVnMBAG4+umUbwGmn132N3fgpzLarFF3XyWmS1zh
D/J07iM/rP8GDO9IskHNHd2phrO0G6KzrcFAnTBHjVv+hCBEfzN/no3FNA9AuC36
mwIDAQAB
-----END PUBLIC KEY-----"""

BUILTIN_VOICES = [
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV421_vivn_streaming", "display_name": "Nhỏ Ngọt Ngào", "resource_id": "7252594014782755330"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "vi_female_huong", "display_name": "Giọng Nữ Phổ Thông", "resource_id": "7264854897953083905"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV074_streaming_dsp", "display_name": "Giọng Bé", "resource_id": "7550087831092251920"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV074_streaming", "display_name": "Cô Gái Hoạt Ngôn", "resource_id": "7102355709945188865"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV075_streaming_vibrato_dsp", "display_name": "Việt Méo", "resource_id": "7569450639810465040"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV562_streaming", "display_name": "Mai", "resource_id": "7483736254694035984"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_yangguangnv_uranus_bigtts", "display_name": "Ban Mai", "resource_id": "7637456432522218773"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_richgirl_uranus_bigtts", "display_name": "Review Phim New", "resource_id": "7637460351541447956"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_quanweinv_uranus_bigtts", "display_name": "Bản Tin 1", "resource_id": "7637458743197732117"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_stokie_uranus_bigtts", "display_name": "Review Phim 4", "resource_id": "7637456729696996628"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_sisi_uranus_bigtts", "display_name": "Bản Tin Nữ", "resource_id": "7637455857285860629"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_daqi_uranus_bigtts", "display_name": "Review Phim 3", "resource_id": "7637451983389019409"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_xyf04auto_uranus_bigtts", "display_name": "Review Phim 2", "resource_id": "7637458743197732117"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_kiwi_uranus_bigtts", "display_name": "Sunny Idol", "resource_id": "7637457995882089749"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV075_streaming_demon_dsp", "display_name": "Kenny Đại Đế", "resource_id": "7569442422665661712"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV075_streaming_robot_dsp", "display_name": "Robot VN", "resource_id": "7538698409633516816"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_male_felipe_uranus_bigtts", "display_name": "Giọng Nam Trầm", "resource_id": "7637456729696996628"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_peiqi_uranus_bigtts", "display_name": "Giọng Gái Mới Lớn", "resource_id": "7637458789033151751"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_xinwenjieshuo_uranus_bigtts", "display_name": "Nam Bản Tin", "resource_id": "7637455039719640327"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "multi_female_tianmeijieshuo_uranus_bigtts", "display_name": "Giọng Thuyết Minh", "resource_id": "7637460417295469832"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV075_streaming", "display_name": "Thanh Niên Tự Tin", "resource_id": "7102355803792740865"},
    {"lan": "vi", "lang": "vi-VN", "voice_type": "BV560_streaming", "display_name": "Alex Đại Đế", "resource_id": "7483736167565758992"},
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _der_value(data: bytes, pos: int, tag: int) -> tuple[bytes, int]:
    if data[pos] != tag:
        raise ValueError("Khóa ký CapCut không hợp lệ")
    pos += 1
    length = data[pos]
    pos += 1
    if length & 0x80:
        size = length & 0x7F
        length = int.from_bytes(data[pos:pos + size], "big")
        pos += size
    return data[pos:pos + length], pos + length


def _public_numbers() -> tuple[int, int]:
    encoded = "".join(line for line in PUBLIC_KEY.splitlines() if not line.startswith("-----"))
    outer, _ = _der_value(base64.b64decode(encoded), 0, 0x30)
    _, pos = _der_value(outer, 0, 0x30)
    bits, _ = _der_value(outer, pos, 0x03)
    sequence, _ = _der_value(bits[1:], 0, 0x30)
    modulus_raw, pos = _der_value(sequence, 0, 0x02)
    exponent_raw, _ = _der_value(sequence, pos, 0x02)
    return int.from_bytes(modulus_raw.lstrip(b"\0"), "big"), int.from_bytes(exponent_raw, "big")


def _rsa_encrypt(message: str) -> str:
    modulus, exponent = _public_numbers()
    key_len = (modulus.bit_length() + 7) // 8
    raw = message.encode("utf-8")
    padding = bytearray()
    while len(padding) < key_len - len(raw) - 3:
        padding.extend(byte for byte in secrets.token_bytes(key_len - len(raw) - 3 - len(padding)) if byte)
    encoded = b"\0\2" + bytes(padding) + b"\0" + raw
    encrypted = pow(int.from_bytes(encoded, "big"), exponent, modulus).to_bytes(key_len, "big")
    return base64.b64encode(encrypted).decode("ascii")


def _device() -> dict[str, str]:
    result = deepcopy(DEFAULT_DEVICE)
    device_id = str(secrets.randbelow(9 * 10**18) + 10**18)
    result.update({"device_id": device_id, "iid": str(secrets.randbelow(9 * 10**18) + 10**18), "tdid": device_id})
    return result


def _query(device: dict[str, str], babi: dict[str, str] | None, region: bool) -> dict[str, str]:
    keys = ("app_name", "device_type", "os_version", "channel", "version_name",
            "device_brand", "device_id", "iid", "version_code", "device_platform", "aid")
    result = {key: device[key] for key in keys}
    if region:
        result["region"] = device["region"]
    if babi is not None:
        result["babi_param"] = _json(babi)
    return result


def _post(path: str, query: dict[str, str], body: dict[str, Any],
          device: dict[str, str], appid: bool) -> dict[str, Any]:
    body_text = _json(body)
    now = str(int(time.time()))
    url = f"{BASE}{path}?{urlencode(query)}"
    headers = {
        "content-type": "application/json", "appvr": device["appvr"],
        "ch": device["channel"], "device-time": now, "lan": device["lan"],
        "loc": device["loc"], "pf": device["pf"], "sign-ver": "1",
        "tdid": device["tdid"], "x-ss-stub": hashlib.md5(body_text.encode()).hexdigest(),
        "x-ss-dp": device["aid"], "x-khronos": now,
        "x-tt-trace-id": f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01",
        "user-agent": "Cronet/TTNetVersion:1d7cc3b1 2025-07-16 QuicVersion:52c2b40d 2025-04-03",
        "accept-encoding": "identity", "store-country-code": device["loc"].lower(),
        "store-country-code-src": "did", "is-dispatch-us-ttp": "0", "is-app-region-us-ttp": "0",
    }
    if appid:
        headers.update({"app-sdk-version": device["appvr"], "appid": device["aid"]})
    sign_text = f"9e2c|{path[-7:]}|3|{device['appvr']}|{now}|{device['tdid']}|11ac"
    headers["sign"] = hashlib.md5(sign_text.encode()).hexdigest()
    request = urllib.request.Request(url, data=body_text.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CapCut API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không kết nối được CapCut API: {exc.reason}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("CapCut API trả dữ liệu không hợp lệ")
    return result


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def synthesize(text: str, voice: str, resource_id: str, rate: float = 1.0,
               cancelled: Any = None) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Nội dung tạo giọng đang trống")
    if len(text) > 280:
        raise ValueError("Một câu CapCut TTS không được dài quá 280 ký tự")
    device = _device()
    babi = {"feature_entrance": "editor", "feature_entrance_detail": "editor-feature-text_to_speech",
            "feature_key": "text_to_speech", "scenario": "video_editor"}
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}" mock_tone_info="" platform="sami" resource_id="{resource_id}" '
        'emotion="" emotion_scale="0" style="" role="" moyin_emotion="" is_clone_tone="false" '
        f'need_subtitle_timestamp="false"><prosody rate="{min(3.0, max(.5, rate))}">{_escape(text)}</prosody>'
        '</voice></speak>'
    )
    extra = _json({"benefit_info": {}})
    raw_sign = f"appid:{device['aid']}&did:{device['device_id']}&creditDisable:false&ssml:{hashlib.md5(ssml.encode()).hexdigest()}&extraInfo:{extra}"
    payload = {"audio_format": "mp3", "babi_param": _json(babi), "credit_disable": False,
               "extra_info": extra, "need_merge_voice": False, "need_subtitle_timestamp": False,
               "scene": "text_to_speech", "ssml": ssml, "sign": _rsa_encrypt(raw_sign)}
    new_body = {"bind_id": str(uuid.uuid4()), "can_queue": True, "enter_from": "text_to_speech",
                "tasks": [{"context": str(uuid.uuid4()), "payload": _json(payload),
                           "req_key": "sami_text_to_speech", "task_version": "v3"}]}
    created = _post("/lv/v1/common_task/new", _query(device, babi, True), new_body, device, True)
    tasks = created.get("data", {}).get("tasks", [])
    if not tasks:
        raise RuntimeError(f"CapCut không tạo được task: {str(created)[:500]}")
    task_id, token = str(tasks[0]["id"]), str(tasks[0]["token"])
    deadline = time.time() + 45
    while time.time() < deadline:
        if cancelled and cancelled():
            raise RuntimeError("Đã hủy tác vụ")
        time.sleep(1.5)
        query_body = {"tasks": [{"bind_id": "", "id": task_id, "req_key": "sami_text_to_speech",
                                 "task_version": "v3", "token": token}]}
        result = _post("/lv/v1/common_task/query", _query(device, None, False), query_body, device, True)
        queried = result.get("data", {}).get("tasks", [])
        if not queried:
            continue
        task = queried[0]
        status = str(task.get("status", "")).lower()
        if status in {"success", "succeed", "succeeded", "done", "completed"}:
            output = task.get("payload", {})
            if isinstance(output, str):
                output = json.loads(output or "{}")
            audio = output.get("audio_subtitles", []) if isinstance(output, dict) else []
            if audio and audio[0].get("speech_url"):
                return str(audio[0]["speech_url"])
            raise RuntimeError("Task CapCut hoàn thành nhưng không có URL audio")
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise RuntimeError(f"CapCut TTS thất bại: {str(task)[:500]}")
    raise TimeoutError("CapCut TTS quá thời gian chờ 45 giây")
