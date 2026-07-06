#!/usr/bin/env python3
"""Weekly ticker 50/200 DMA monitor.

Fetches daily prices, calculates 50-day and 200-day simple moving
averages from closing prices, and prints a compact status report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from zoneinfo import ZoneInfo


DEFAULT_SYMBOL = "QQQ"
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MonitorResult:
    symbol: str
    as_of: str
    close: float
    sma_50: float
    sma_200: float
    close_vs_50_points: float
    close_vs_50_pct: float
    close_vs_200_points: float
    close_vs_200_pct: float
    status_50: str
    status_200: str


def yahoo_chart_url(symbol: str) -> str:
    encoded_symbol = urllib.parse.quote(symbol.upper())
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        "?range=2y&interval=1d&events=history"
    )


def fetch_daily_closes(symbol: str) -> list[tuple[str, float]]:
    url = yahoo_chart_url(symbol)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "dma-monitor/1.0",
            "Accept": "application/json,*/*",
        },
    )
    context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to fetch price data from {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("price feed did not return valid JSON") from exc

    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        timezone_name = result["meta"].get("exchangeTimezoneName", "America/New_York")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("price feed did not return the expected chart data") from exc

    market_tz = ZoneInfo(timezone_name)
    daily_closes: list[tuple[str, float]] = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        as_of = dt.datetime.fromtimestamp(timestamp, market_tz).date().isoformat()
        daily_closes.append((as_of, float(close)))

    return daily_closes


def calculate_result(symbol: str, closes: list[tuple[str, float]]) -> MonitorResult:
    if len(closes) < 200:
        raise RuntimeError(
            f"{symbol.upper()} needs at least 200 daily closes, got {len(closes)}"
        )

    as_of, latest_close = closes[-1]
    sma_50 = sum(close for _, close in closes[-50:]) / 50
    sma_200 = sum(close for _, close in closes[-200:]) / 200

    close_vs_50 = latest_close - sma_50
    close_vs_200 = latest_close - sma_200

    return MonitorResult(
        symbol=symbol.upper(),
        as_of=as_of,
        close=latest_close,
        sma_50=sma_50,
        sma_200=sma_200,
        close_vs_50_points=close_vs_50,
        close_vs_50_pct=(close_vs_50 / sma_50) * 100,
        close_vs_200_points=close_vs_200,
        close_vs_200_pct=(close_vs_200 / sma_200) * 100,
        status_50="above" if close_vs_50 >= 0 else "below",
        status_200="above" if close_vs_200 >= 0 else "below",
    )


def format_report(result: MonitorResult) -> str:
    generated = dt.datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M %Z")
    return "\n".join(
        [
            f"{result.symbol} DMA monitor - generated {generated}",
            f"As of close: {result.as_of}",
            f"{result.symbol} close: ${result.close:.2f}",
            f"50 DMA: ${result.sma_50:.2f} ({result.status_50} by "
            f"${abs(result.close_vs_50_points):.2f}, {abs(result.close_vs_50_pct):.2f}%)",
            f"200 DMA: ${result.sma_200:.2f} ({result.status_200} by "
            f"${abs(result.close_vs_200_points):.2f}, {abs(result.close_vs_200_pct):.2f}%)",
        ]
    )


def format_slack_report(result: MonitorResult) -> str:
    generated = dt.datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M %Z")
    return "\n".join(
        [
            f"*{result.symbol} DMA monitor* - generated {generated}",
            f"*As of close:* {result.as_of}",
            f"*{result.symbol} close:* ${result.close:.2f}",
            f"*50 DMA:* ${result.sma_50:.2f} ({result.status_50} by "
            f"${abs(result.close_vs_50_points):.2f}, {abs(result.close_vs_50_pct):.2f}%)",
            f"*200 DMA:* ${result.sma_200:.2f} ({result.status_200} by "
            f"${abs(result.close_vs_200_points):.2f}, {abs(result.close_vs_200_pct):.2f}%)",
        ]
    )


def notify_macos(message: str) -> None:
    title = "DMA Monitor"
    script = (
        "display notification "
        + json.dumps(message)
        + " with title "
        + json.dumps(title)
    )
    subprocess.run(["osascript", "-e", script], check=False)


def send_email(message: str, recipient: str) -> None:
    smtp_host = env_value("DMA_MONITOR_SMTP_HOST", "QQQ_DMA_SMTP_HOST")
    smtp_port = int(env_value("DMA_MONITOR_SMTP_PORT", "QQQ_DMA_SMTP_PORT", "587"))
    smtp_user = env_value("DMA_MONITOR_SMTP_USER", "QQQ_DMA_SMTP_USER")
    smtp_password = env_value("DMA_MONITOR_SMTP_PASSWORD", "QQQ_DMA_SMTP_PASSWORD")
    sender = env_value("DMA_MONITOR_EMAIL_FROM", "QQQ_DMA_EMAIL_FROM") or smtp_user

    missing = [
        name
        for name, value in {
            "DMA_MONITOR_SMTP_HOST": smtp_host,
            "DMA_MONITOR_SMTP_USER": smtp_user,
            "DMA_MONITOR_SMTP_PASSWORD": smtp_password,
            "DMA_MONITOR_EMAIL_FROM or DMA_MONITOR_SMTP_USER": sender,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("missing email configuration: " + ", ".join(missing))

    email = EmailMessage()
    email["Subject"] = "DMA weekly monitor"
    email["From"] = sender
    email["To"] = recipient
    email.set_content(message)

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as smtp:
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(email)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(email)


def send_slack(message: str, webhook_urls: list[str]) -> None:
    if not webhook_urls:
        raise RuntimeError("missing Slack configuration: DMA_MONITOR_SLACK_WEBHOOK_URLS")

    payload = json.dumps({"text": message}).encode("utf-8")
    for webhook_url in webhook_urls:
        request = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "dma-monitor/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                if response.status >= 300:
                    raise RuntimeError(
                        f"Slack webhook returned HTTP {response.status}: {response_body}"
                    )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Slack webhook returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to send Slack webhook: {exc}") from exc


def parse_slack_webhook_urls() -> list[str]:
    raw_urls = env_value(
        "DMA_MONITOR_SLACK_WEBHOOK_URLS",
        "QQQ_DMA_SLACK_WEBHOOK_URLS",
        "",
    )
    return [url.strip() for url in raw_urls.split(",") if url.strip()]


def env_value(primary: str, legacy: str, default: str | None = None) -> str | None:
    return os.environ.get(primary) or os.environ.get(legacy) or default


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor a ticker against 50/200 DMA.")
    parser.add_argument(
        "--symbol",
        default=env_value("DMA_MONITOR_SYMBOL", "QQQ_DMA_SYMBOL", DEFAULT_SYMBOL),
        help="ticker symbol to monitor, default: QQQ or DMA_MONITOR_SYMBOL",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--notify",
        action="store_true",
        help="also send a macOS notification with the report",
    )
    parser.add_argument("--email-to", help="send the report to this email address")
    parser.add_argument(
        "--slack",
        action="store_true",
        help="send the report to Slack webhook URLs from QQQ_DMA_SLACK_WEBHOOK_URLS",
    )
    args = parser.parse_args()

    symbol = args.symbol.strip().upper()
    result = calculate_result(symbol, fetch_daily_closes(symbol))
    report = format_report(result)
    slack_report = format_slack_report(result)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(report)

    if args.notify:
        notify_macos(report)

    if args.email_to:
        send_email(report, args.email_to)

    if args.slack:
        send_slack(slack_report, parse_slack_webhook_urls())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
