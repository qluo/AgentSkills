---
name: ticker-dma-monitor
description: Monitor stock or ETF tickers against 50-day and 200-day daily moving averages, generate text/JSON/Slack/email reports, and set up unattended weekly cron delivery. Use when Codex needs to create, run, adapt, or schedule a ticker DMA monitor for symbols such as QQQ, SPY, AAPL, MSFT, or other Yahoo Finance-compatible tickers.
---

# Ticker DMA Monitor

## Overview

Use this skill to monitor one or more Yahoo Finance-compatible tickers against their 50-day and 200-day simple moving averages. Prefer the bundled script over rewriting the monitor from scratch.

Bundled script:

```text
scripts/dma_monitor.py
```

It fetches daily closes from Yahoo Finance's chart endpoint, calculates the latest close versus the 50 DMA and 200 DMA, prints a report, and can post to Slack webhooks or send SMTP email.

## Quick Start

Run a one-off report:

```bash
python3 scripts/dma_monitor.py --symbol QQQ
python3 scripts/dma_monitor.py --symbol SPY --json
```

Post to Slack:

```bash
export DMA_MONITOR_SYMBOL=QQQ
export DMA_MONITOR_SLACK_WEBHOOK_URLS='https://hooks.slack.com/services/...'
python3 scripts/dma_monitor.py --slack
```

Send email:

```bash
export DMA_MONITOR_SMTP_HOST=smtp.gmail.com
export DMA_MONITOR_SMTP_PORT=587
export DMA_MONITOR_SMTP_USER=you@example.com
export DMA_MONITOR_SMTP_PASSWORD='app-password'
export DMA_MONITOR_EMAIL_FROM=you@example.com
python3 scripts/dma_monitor.py --symbol QQQ --email-to recipient@example.com
```

## Workflow

1. Identify the ticker symbol and delivery target.
2. Copy `scripts/dma_monitor.py` into the user's project if they need a persistent local monitor.
3. Configure secrets in a local env file, never directly in tracked source.
4. Run the script once and verify the report before scheduling.
5. For cron, source the env file and append logs to local files.

Example cron entry for Monday 10:00 AM Eastern Slack delivery:

```cron
SHELL=/bin/sh
PATH=/usr/bin:/bin:/usr/sbin:/sbin
TZ=America/New_York

0 10 * * 1 . /path/to/dma_monitor.env; cd /path/to/project && /usr/bin/python3 dma_monitor.py --slack >> dma_monitor.log 2>> dma_monitor.err.log
```

Example env file:

```bash
export DMA_MONITOR_SYMBOL=QQQ
export DMA_MONITOR_SLACK_WEBHOOK_URLS=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

Set env file permissions to `600` when it contains secrets.

## Configuration

Supported environment variables:

```text
DMA_MONITOR_SYMBOL
DMA_MONITOR_SLACK_WEBHOOK_URLS
DMA_MONITOR_SMTP_HOST
DMA_MONITOR_SMTP_PORT
DMA_MONITOR_SMTP_USER
DMA_MONITOR_SMTP_PASSWORD
DMA_MONITOR_EMAIL_FROM
DMA_MONITOR_EMAIL_TO
```

`DMA_MONITOR_SLACK_WEBHOOK_URLS` accepts comma-separated webhook URLs. Slack incoming webhooks are usually bound to a specific channel, so multiple channels usually require multiple webhook URLs.

## Validation

Always run at least:

```bash
python3 -m py_compile dma_monitor.py
python3 dma_monitor.py --symbol QQQ
```

If testing Slack delivery, send one explicit test post after the user provides or confirms the webhook URL. Treat webhook URLs as secrets and do not echo them back in final responses.

## Notes

- The script requires network access to fetch Yahoo Finance prices and post to Slack or SMTP.
- The 50 DMA and 200 DMA are simple moving averages over the latest 50 and 200 daily closes returned by the price feed.
- Symbols are uppercased and URL-encoded before calling Yahoo Finance.
- For tickers with less than 200 closes, report the insufficient-history error rather than fabricating values.
