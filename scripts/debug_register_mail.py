#!/usr/bin/env python3
"""
独立调试 Exa 注册流程（通用邮箱版本）。

支持邮箱提供商：
- duckmail
- moemail
- freemail
- gptmail
- cfmail

用途：
- 不依赖前端或任务队列，直接验证「邮箱创建 -> OTP -> Exa 自动化 -> 创建 API Key」全链路。
- 适合定位注册失败是出在邮箱侧、OTP 收取、还是 Exa 页面自动化。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import config
from core.exa_automation import ExaAutomation
from core.mail_providers import create_temp_mail_client


SUPPORTED_PROVIDERS = ("duckmail", "moemail", "freemail", "gptmail", "cfmail")

ENV_KEYS = {
    "duckmail": {
        "base_url": "DUCKMAIL_BASE_URL",
        "api_key": "DUCKMAIL_API_KEY",
        "domain": "REGISTER_DOMAIN",
        "verify_ssl": "DUCKMAIL_VERIFY_SSL",
    },
    "moemail": {
        "base_url": "MOEMAIL_BASE_URL",
        "api_key": "MOEMAIL_API_KEY",
        "domain": "MOEMAIL_DOMAIN",
    },
    "freemail": {
        "base_url": "FREEMAIL_BASE_URL",
        "jwt_token": "FREEMAIL_JWT_TOKEN",
        "domain": "FREEMAIL_DOMAIN",
        "verify_ssl": "FREEMAIL_VERIFY_SSL",
    },
    "gptmail": {
        "base_url": "GPTMAIL_BASE_URL",
        "api_key": "GPTMAIL_API_KEY",
        "domain": "GPTMAIL_DOMAIN",
        "verify_ssl": "GPTMAIL_VERIFY_SSL",
    },
    "cfmail": {
        "base_url": "CFMAIL_BASE_URL",
        "api_key": "CFMAIL_API_KEY",
        "domain": "CFMAIL_DOMAIN",
        "verify_ssl": "CFMAIL_VERIFY_SSL",
    },
}


@dataclass
class MailSettings:
    provider: str
    base_url: str
    domain: str
    api_key: str
    jwt_token: str
    verify_ssl: bool
    mail_proxy: str


def _parse_bool_text(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


def _mask(value: str, head: int = 8, tail: int = 4) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= head + tail:
        return text[: max(2, len(text) // 2)] + "****"
    return f"{text[:head]}...{text[-tail:]}"


def _logger(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _env(provider: str, key: str) -> str:
    env_key = ENV_KEYS.get(provider, {}).get(key, "")
    return (os.environ.get(env_key, "") or "").strip() if env_key else ""


def _default_provider() -> str:
    candidate = (config.basic.temp_mail_provider or "").strip().lower()
    return candidate if candidate in SUPPORTED_PROVIDERS else "duckmail"


def _resolve_mail_settings(args: argparse.Namespace) -> MailSettings:
    provider = (args.mail_provider or "").strip().lower() or _default_provider()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的邮箱提供商: {provider}")

    if provider == "duckmail":
        base_url = (args.mail_base_url or _env(provider, "base_url") or config.basic.duckmail_base_url or "").strip()
        domain = (args.mail_domain or _env(provider, "domain") or config.basic.register_domain or "").strip()
        api_key = (args.mail_api_key or _env(provider, "api_key") or config.basic.duckmail_api_key or "").strip()
        verify_default = bool(config.basic.duckmail_verify_ssl)
    elif provider == "moemail":
        base_url = (args.mail_base_url or _env(provider, "base_url") or config.basic.moemail_base_url or "").strip()
        domain = (args.mail_domain or _env(provider, "domain") or config.basic.moemail_domain or "").strip()
        api_key = (args.mail_api_key or _env(provider, "api_key") or config.basic.moemail_api_key or "").strip()
        verify_default = True
    elif provider == "freemail":
        base_url = (args.mail_base_url or _env(provider, "base_url") or config.basic.freemail_base_url or "").strip()
        domain = (args.mail_domain or _env(provider, "domain") or config.basic.freemail_domain or "").strip()
        api_key = ""
        verify_default = bool(config.basic.freemail_verify_ssl)
    elif provider == "gptmail":
        base_url = (args.mail_base_url or _env(provider, "base_url") or config.basic.gptmail_base_url or "").strip()
        domain = (args.mail_domain or _env(provider, "domain") or config.basic.gptmail_domain or "").strip()
        api_key = (args.mail_api_key or _env(provider, "api_key") or config.basic.gptmail_api_key or "").strip()
        verify_default = bool(config.basic.gptmail_verify_ssl)
    else:  # cfmail
        base_url = (args.mail_base_url or _env(provider, "base_url") or config.basic.cfmail_base_url or "").strip()
        domain = (args.mail_domain or _env(provider, "domain") or config.basic.cfmail_domain or "").strip()
        api_key = (args.mail_api_key or _env(provider, "api_key") or config.basic.cfmail_api_key or "").strip()
        verify_default = bool(config.basic.cfmail_verify_ssl)

    jwt_token = (args.mail_jwt_token or _env(provider, "jwt_token") or config.basic.freemail_jwt_token or "").strip()
    env_ssl = _env(provider, "verify_ssl")
    verify_ssl = verify_default
    if env_ssl:
        verify_ssl = _parse_bool_text(env_ssl, verify_default)
    if args.mail_verify_ssl is not None:
        verify_ssl = bool(args.mail_verify_ssl)

    return MailSettings(
        provider=provider,
        base_url=base_url,
        domain=domain,
        api_key=api_key,
        jwt_token=jwt_token,
        verify_ssl=verify_ssl,
        mail_proxy=(args.mail_proxy or "").strip(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立调试 Exa 注册流程（通用邮箱版本）")
    parser.add_argument(
        "--mail-provider",
        choices=SUPPORTED_PROVIDERS,
        default="",
        help="邮箱提供商（默认读取系统设置 temp_mail_provider）",
    )
    parser.add_argument(
        "--mail-base-url",
        default="",
        help="邮箱 API 地址（未填则按 provider 从环境变量/系统设置读取）",
    )
    parser.add_argument(
        "--mail-api-key",
        default="",
        help="邮箱 API Key（duckmail/moemail/gptmail/cfmail）",
    )
    parser.add_argument(
        "--mail-jwt-token",
        default="",
        help="邮箱 JWT Token（freemail）",
    )
    parser.add_argument(
        "--mail-domain",
        default="",
        help="邮箱域名（可选）",
    )
    parser.add_argument(
        "--mail-verify-ssl",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="邮箱请求是否校验 SSL（不传则走 provider 默认/系统设置）",
    )
    parser.add_argument(
        "--mail-proxy",
        default="",
        help="邮箱请求代理地址（可选）",
    )

    parser.add_argument(
        "--browser-proxy",
        default="",
        help="Playwright 浏览器代理地址（可选），例如 http://127.0.0.1:7890",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120000,
        help="Playwright 页面超时（毫秒）",
    )
    parser.add_argument(
        "--redeem-coupon",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否在注册后自动尝试兑换优惠码",
    )
    parser.add_argument(
        "--coupon-code",
        default="",
        help="优惠码（与 --redeem-coupon 一起使用）",
    )
    parser.add_argument(
        "--result-json",
        default="",
        help="将完整结果写入 JSON 文件（可选，包含敏感信息）",
    )
    parser.add_argument(
        "--show-full-key",
        action="store_true",
        help="输出完整 Exa API Key（默认仅输出掩码）",
    )
    return parser.parse_args()


def main() -> int:
    _ensure_utf8_stdout()
    args = parse_args()

    try:
        settings = _resolve_mail_settings(args)
    except Exception as exc:
        print(f"ERROR: 邮箱配置解析失败: {exc}")
        return 2

    print(f"MAIL_PROVIDER: {settings.provider}")
    print("STEP 1/3: 创建临时邮箱")
    mail_client = create_temp_mail_client(
        settings.provider,
        domain=settings.domain or None,
        proxy=settings.mail_proxy or None,
        log_cb=_logger,
        base_url=settings.base_url or None,
        api_key=settings.api_key or None,
        jwt_token=settings.jwt_token or None,
        verify_ssl=settings.verify_ssl,
    )
    if not mail_client.register_account(domain=settings.domain or None):
        print("FINAL_SUCCESS: False")
        print("ERROR: 临时邮箱创建失败")
        return 3

    print(f"MAILBOX: {getattr(mail_client, 'email', '')}")

    print("STEP 2/3: 执行 Exa OTP 登录与初始化")
    automation = ExaAutomation(
        proxy=(args.browser_proxy or "").strip(),
        timeout_ms=max(15000, int(args.timeout_ms)),
        log_callback=_logger,
    )

    result = automation.register_and_setup(
        email=getattr(mail_client, "email", "") or "",
        mail_client=mail_client,
        coupon_code=(args.coupon_code or "").strip(),
        redeem_coupon=bool(args.redeem_coupon),
    )

    if args.result_json:
        result_path = Path(args.result_json).expanduser().resolve()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"RESULT_JSON: {result_path}")

    if not result.get("success"):
        print("FINAL_SUCCESS: False")
        print(f"ERROR: {result.get('error')}")
        return 1

    config_data = result.get("config", {}) or {}
    exa_key = str(config_data.get("exa_api_key") or "")
    show_key = exa_key if args.show_full_key else _mask(exa_key)

    print("STEP 3/3: 完成")
    print("FINAL_SUCCESS: True")
    print(f"ACCOUNT_ID: {config_data.get('id')}")
    print(f"EXA_API_KEY: {show_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
