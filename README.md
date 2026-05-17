# 🤖 AI Automation Pipeline

A production-ready Python framework that **scrapes the web**, **analyses content with GPT-4o**, **generates HTML intelligence reports**, and **delivers them via Email & Slack** — fully automated, on a schedule.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/GPT--4o-OpenAI-412991?style=flat-square&logo=openai&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/status-production--ready-brightgreen?style=flat-square)

---

## ✨ Features

- **Async web scraping** — concurrent fetching with `httpx` + `BeautifulSoup`, noise-stripped content
- **GPT-4o analysis** — structured JSON output: summary, key points, sentiment, entities, relevance score
- **HTML report generation** — dark-themed, styled reports via `Jinja2`
- **Email delivery** — SMTP or SendGrid with HTML + plain-text fallback
- **Slack notifications** — rich Block Kit messages with a "View Report" button
- **Cron scheduling** — APScheduler with configurable cron expression
- **Web dashboard** — view, filter, and drill into past reports (React UI)

---

## 🏗️ Architecture

```
TARGET URLS
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  scraper.py │────▶│ analyser.py  │────▶│  reporter.py │
│  httpx+BS4  │     │   GPT-4o     │     │   Jinja2     │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                              ┌──────────────────┼──────────────────┐
                              ▼                  ▼                  ▼
                       ┌────────────┐   ┌─────────────────┐  ┌──────────┐
                       │ emailer.py │   │slack_notifier.py│  │ reports/ │
                       │SMTP/SndGrd │   │  Webhook+Blocks │  │  *.html  │
                       └────────────┘   └─────────────────┘  └──────────┘

Orchestrated by pipeline.py · Scheduled by scheduler.py (APScheduler cron)
```

---

## 📁 Project Structure

```
ai-automation-pipeline/
├── scraper.py           # Async web scraper (httpx + BeautifulSoup)
├── analyser.py          # GPT-4o content analyser
├── reporter.py          # Jinja2 HTML report generator
├── emailer.py           # SMTP / SendGrid email delivery
├── slack_notifier.py    # Slack Webhook notifications
├── scheduler.py         # APScheduler cron orchestrator
├── pipeline.py          # Master runner — wires everything together
├── templates/           # (optional) External Jinja2 templates
├── reports/             # Generated HTML reports (auto-created)
├── .env.example         # Environment variable reference
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/sarahsair25/-AI-Powered-Python-Script-Runner-U.git
cd ai-automation-pipeline
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see [Environment Variables](#-environment-variables) below).

### 3. Run manually

```bash
python pipeline.py
```

### 4. Start the scheduler

```bash
python scheduler.py
```

The scheduler runs the pipeline on a cron expression (default: **weekdays at 08:00 UTC**).

---

## 📦 Requirements

```txt
httpx>=0.27
beautifulsoup4>=4.12
openai>=1.30
jinja2>=3.1
sendgrid>=6.11
apscheduler>=3.10
python-dotenv>=1.0
```

Install all at once:

```bash
pip install httpx beautifulsoup4 openai jinja2 sendgrid apscheduler python-dotenv
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in your values. **Never commit `.env` to version control.**

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key for GPT-4o |
| `SMTP_HOST` | ✅ | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | ➖ | SMTP port — defaults to `587` |
| `SMTP_USER` | ✅ | SMTP login username |
| `SMTP_PASS` | ✅ | SMTP password or app password |
| `EMAIL_FROM` | ✅ | Sender email address |
| `EMAIL_RECIPIENTS` | ✅ | Comma-separated recipient emails |
| `SENDGRID_API_KEY` | ➖ | Use instead of SMTP if preferred |
| `SLACK_WEBHOOK_URL` | ➖ | Slack Incoming Webhook URL |
| `TARGET_URLS` | ✅ | Comma-separated URLs to scrape |
| `TOPIC` | ✅ | Intelligence topic / GPT-4 focus |
| `CRON` | ➖ | Cron expression — defaults to `0 8 * * 1-5` |
| `REPORT_DIR` | ➖ | Report output directory — defaults to `./reports` |

---

## 🔧 Configuration Examples

**Run every day at 07:00 UTC:**
```bash
CRON="0 7 * * *"
```

**Monitor multiple tech news sources:**
```bash
TARGET_URLS="https://techcrunch.com,https://theverge.com,https://news.ycombinator.com,https://venturebeat.com"
TOPIC="AI and machine learning industry news"
```

**Send to multiple recipients:**
```bash
EMAIL_RECIPIENTS="alice@example.com,bob@example.com,team@example.com"
```

---

## 📊 Sample Report Output

Each HTML report includes:

- **Source title & URL** with relevance score (0–10)
- **AI-generated summary** (2–3 sentences)
- **Key points** extracted by GPT-4o
- **Sentiment** classification (positive / neutral / negative)
- **Named entities** (people, organisations, products)

Reports are saved to `./reports/report_YYYYMMDD_HHMM.html` and delivered via email and Slack simultaneously.

---

## 🌐 Deployment

### VPS / Linux server

```bash
# Run scheduler as a background process
nohup python scheduler.py &> scheduler.log &

# Or use systemd for production
sudo nano /etc/systemd/system/pipeline.service
```

### Railway / Fly.io

```bash
# Set environment variables via dashboard, then:
railway up
# or
fly deploy
```

### Docker *(coming soon)*

```bash
docker compose up -d
```

---

## 🛣️ Roadmap

- [ ] `Dockerfile` + `docker-compose.yml` for one-command deployment
- [ ] Flask/FastAPI backend to serve reports to the web dashboard
- [ ] `retry.py` — exponential backoff for failed scrapes and API calls
- [ ] Source manager UI — add/remove URLs without touching `.env`
- [ ] Multi-topic support — parallel pipelines with dashboard comparison
- [ ] RSS feed support as an alternative to direct URL scraping
- [ ] LLM provider abstraction — swap GPT-4o for Claude, Gemini, etc.

---

## 🤝 Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## 📄 License

MIT © 2026 — feel free to use, modify, and distribute.

---

> Built with ❤️ using Python, OpenAI GPT-4o, and a healthy obsession with automation.
