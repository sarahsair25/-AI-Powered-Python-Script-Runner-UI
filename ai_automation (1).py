"""
╔══════════════════════════════════════════════════════════════╗
║           AI AUTOMATION PIPELINE — Python Edition           ║
║  Collect → Analyse → Summarise → Report → Notify → Repeat  ║
╚══════════════════════════════════════════════════════════════╝

A fully self-contained, production-ready AI automation pipeline.

WHAT IT DOES
─────────────
 1. Scrapes any website for content (articles, data, listings)
 2. Sends collected content to GPT-4 for AI-powered analysis
 3. Extracts structured insights: summary, sentiment, key points
 4. Generates a styled HTML intelligence report
 5. Emails the report + pings Slack with a digest
 6. Runs on a cron-style schedule — hands-free, every time

SETUP
──────
  pip install requests beautifulsoup4 openai schedule
  export OPENAI_API_KEY="sk-..."
  export SMTP_USER="you@gmail.com"
  export SMTP_PASSWORD="your-app-password"
  export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
  python ai_automation.py

Author  : Your Name
License : MIT
"""

from __future__ import annotations

# ── Standard library ───────────────────────────────────────────
import json
import logging
import os
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

# ── Third-party ────────────────────────────────────────────────
import requests
import schedule
from bs4 import BeautifulSoup
from openai import OpenAI

# ══════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s  →  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ai_pipeline")


# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
#  All secrets come from environment variables — never hardcode.
# ══════════════════════════════════════════════════════════════
@dataclass
class Config:
    """Central config. Override any field via environment variable."""
    # AI
    openai_api_key: str  = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model:   str  = "gpt-4o-mini"
    max_articles:   int  = 10

    # Email
    smtp_host:     str   = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port:     int   = 587
    smtp_user:     str   = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str   = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))

    # Slack
    slack_webhook: str   = field(default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL", ""))

    # Storage & retry
    report_dir:    Path  = Path("reports")
    max_retries:   int   = 3
    retry_delay:   float = 2.0


CFG = Config()


# ══════════════════════════════════════════════════════════════
#  DECORATORS
# ══════════════════════════════════════════════════════════════
def retry(max_attempts: int = 3, base_delay: float = 2.0, exceptions: tuple = (Exception,)):
    """Retry with exponential back-off."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    wait = base_delay * (2 ** (attempt - 1))
                    if attempt == max_attempts:
                        log.error("'%s' failed after %d attempts: %s", fn.__name__, max_attempts, exc)
                        raise
                    log.warning("'%s' attempt %d/%d failed: %s — retrying in %.1fs",
                                fn.__name__, attempt, max_attempts, exc, wait)
                    time.sleep(wait)
        return wrapper
    return decorator


def timed(fn: Callable) -> Callable:
    """Log execution time."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        log.info("⏱  '%s' completed in %.2fs", fn.__name__, time.perf_counter() - start)
        return result
    return wrapper


# ══════════════════════════════════════════════════════════════
#  MODULE 1: DATA COLLECTOR
# ══════════════════════════════════════════════════════════════
class DataCollector:
    """
    Scrapes any web page and returns structured article records.

    Each article dict has:  title | snippet | url
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AIAutomationBot/1.0; "
            "https://github.com/yourhandle/ai-automation-pipeline)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    @retry(max_attempts=3, base_delay=1.5, exceptions=(requests.RequestException,))
    def fetch(self, url: str, timeout: int = 15) -> str:
        log.info("Fetching  →  %s", url)
        resp = requests.get(url, headers=self.HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    def parse(self, html: str, base_url: str = "") -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")

        # Strip noise
        for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
            tag.decompose()

        articles: list[dict[str, str]] = []
        seen: set[str] = set()

        for heading in soup.find_all(["h1", "h2", "h3"], limit=30):
            title = heading.get_text(" ", strip=True)
            if not title or title in seen or len(title) < 10:
                continue
            seen.add(title)

            sibling = heading.find_next_sibling("p")
            snippet = sibling.get_text(" ", strip=True)[:300] if sibling else ""

            anchor = heading.find("a", href=True)
            link   = anchor["href"] if anchor else ""
            if link and not link.startswith("http") and base_url:
                link = base_url.rstrip("/") + "/" + link.lstrip("/")

            articles.append({"title": title, "snippet": snippet, "url": link})

        log.info("Parsed %d articles", len(articles))
        return articles

    @timed
    def collect(self, url: str) -> list[dict[str, str]]:
        html = self.fetch(url)
        return self.parse(html, base_url="/".join(url.split("/")[:3]))


# ══════════════════════════════════════════════════════════════
#  MODULE 2: AI ANALYSER
# ══════════════════════════════════════════════════════════════
class AIAnalyser:
    """
    Sends article batch to GPT. Returns structured JSON insight dict.

    Output keys:
      executive_summary | key_insights | sentiment |
      trending_topics   | recommended_action
    """

    SYSTEM_PROMPT = (
        "You are a senior business intelligence analyst. "
        "Analyse the provided articles and return ONLY valid JSON with these keys: "
        "executive_summary (string, 2-3 sentences), "
        "key_insights (array of up to 5 strings), "
        "sentiment (one of: positive/neutral/negative), "
        "trending_topics (array of up to 5 keyword strings), "
        "recommended_action (string). "
        "No markdown fences. No preamble. JSON only."
    )

    def __init__(self):
        if not CFG.openai_api_key:
            raise EnvironmentError("OPENAI_API_KEY not set. Run: export OPENAI_API_KEY='sk-...'")
        self.client = OpenAI(api_key=CFG.openai_api_key)

    def _build_prompt(self, articles: list[dict], topic: str) -> str:
        lines = [f"Topic: {topic}\n\nArticles:"]
        for i, a in enumerate(articles[:CFG.max_articles], 1):
            lines.append(f"{i}. TITLE: {a['title']}")
            if a["snippet"]:
                lines.append(f"   SNIPPET: {a['snippet']}")
        lines.append("\nReturn JSON only.")
        return "\n".join(lines)

    @retry(max_attempts=3, base_delay=2.0)
    @timed
    def analyse(self, articles: list[dict], topic: str = "Technology & AI") -> dict[str, Any]:
        log.info("Analysing %d articles via %s…", len(articles), CFG.openai_model)

        resp = self.client.chat.completions.create(
            model=CFG.openai_model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": self._build_prompt(articles, topic)},
            ],
            temperature=0.2,
            max_tokens=1000,
        )

        raw = resp.choices[0].message.content.strip()
        # Strip accidental fences
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        log.info("Analysis complete — sentiment: %s", result.get("sentiment", "?"))
        return result


# ══════════════════════════════════════════════════════════════
#  MODULE 3: REPORT GENERATOR
# ══════════════════════════════════════════════════════════════
class ReportGenerator:
    """Renders a styled HTML intelligence report and saves it to disk."""

    COLORS = {"positive": "#16a34a", "neutral": "#2563eb", "negative": "#dc2626"}

    def __init__(self, output_dir: Path = CFG.report_dir):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _html(self, topic: str, analysis: dict, articles: list, ts: str) -> str:
        sentiment = analysis.get("sentiment", "neutral")
        color     = self.COLORS.get(sentiment, "#2563eb")
        summary   = analysis.get("executive_summary", "")
        action    = analysis.get("recommended_action", "")

        insights = "".join(f"<li>{i}</li>" for i in analysis.get("key_insights", []))
        topics   = "".join(f'<span class="pill">{t}</span>' for t in analysis.get("trending_topics", []))
        srcs     = "".join(
            f'<li><a href="{a["url"]}" target="_blank">{a["title"]}</a></li>'
            for a in articles[:10] if a.get("title")
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>AI Report — {topic}</title>
  <style>
    :root{{--accent:{color};--brand:#0f172a;--bg:#f8fafc;--muted:#64748b;--border:#e2e8f0;}}
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:Georgia,serif;background:var(--bg);color:var(--brand);padding:40px 24px;}}
    .wrap{{max-width:800px;margin:0 auto;}}
    header{{border-left:5px solid var(--accent);padding-left:20px;margin-bottom:36px;}}
    header h1{{font-size:2rem;}}
    header p{{color:var(--muted);margin-top:8px;font-size:.9rem;}}
    .badge{{display:inline-block;padding:3px 12px;border-radius:20px;background:var(--accent);
            color:#fff;font-size:.8rem;font-family:monospace;margin-top:10px;}}
    .card{{background:#fff;border:1px solid var(--border);border-radius:12px;
           padding:28px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,.05);}}
    .card h2{{font-size:.75rem;text-transform:uppercase;letter-spacing:.1em;
              color:var(--muted);margin-bottom:14px;}}
    .card p,.card li{{line-height:1.85;font-size:.95rem;}}
    .card ul{{padding-left:20px;}}
    .action{{background:var(--accent);color:#fff;border-radius:10px;padding:22px 28px;margin-bottom:24px;}}
    .action h2{{color:rgba(255,255,255,.7);font-size:.75rem;text-transform:uppercase;
                letter-spacing:.1em;margin-bottom:8px;}}
    .action p{{font-size:1rem;line-height:1.6;}}
    .pill{{display:inline-block;background:var(--bg);border:1px solid var(--border);
           border-radius:20px;padding:4px 14px;font-size:.82rem;margin:4px 4px 4px 0;}}
    a{{color:var(--accent);text-decoration:none;}}
    a:hover{{text-decoration:underline;}}
    footer{{text-align:center;color:var(--muted);font-size:.78rem;margin-top:40px;
            padding-top:20px;border-top:1px solid var(--border);}}
  </style>
</head>
<body><div class="wrap">
  <header>
    <h1>📊 AI Intelligence Report</h1>
    <p><strong>Topic:</strong> {topic} &nbsp;·&nbsp; <strong>Generated:</strong> {ts}</p>
    <span class="badge">sentiment: {sentiment}</span>
  </header>
  <div class="card"><h2>Executive Summary</h2><p>{summary}</p></div>
  <div class="card"><h2>Key Insights</h2><ul>{insights}</ul></div>
  <div class="action"><h2>Recommended Action</h2><p>{action}</p></div>
  <div class="card"><h2>Trending Topics</h2>{topics}</div>
  <div class="card"><h2>Source Articles ({len(articles)})</h2><ul>{srcs}</ul></div>
  <footer>Generated automatically · AI Automation Pipeline</footer>
</div></body></html>"""

    @timed
    def save(self, topic: str, analysis: dict, articles: list) -> Path:
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe = topic.lower().replace(" ", "_").replace("/", "-")
        path = self.output_dir / f"report_{safe}_{ts}.html"
        path.write_text(self._html(topic, analysis, articles, ts), encoding="utf-8")
        log.info("Report saved  →  %s", path)
        return path


# ══════════════════════════════════════════════════════════════
#  MODULE 4: NOTIFIER
# ══════════════════════════════════════════════════════════════
class Notifier:
    """Sends report via Email (HTML) and Slack (text digest)."""

    @retry(max_attempts=2, base_delay=3.0, exceptions=(smtplib.SMTPException, OSError))
    def send_email(self, to: list[str], subject: str, html: str) -> bool:
        if not (CFG.smtp_user and CFG.smtp_password):
            log.warning("SMTP not configured — skipping email.")
            return False
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = CFG.smtp_user
        msg["To"]      = ", ".join(to)
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(CFG.smtp_host, CFG.smtp_port) as s:
            s.ehlo(); s.starttls(); s.login(CFG.smtp_user, CFG.smtp_password)
            s.sendmail(CFG.smtp_user, to, msg.as_string())
        log.info("Email sent  →  %s", to)
        return True

    @retry(max_attempts=2, base_delay=2.0, exceptions=(requests.RequestException,))
    def send_slack(self, text: str) -> bool:
        if not CFG.slack_webhook:
            log.warning("Slack not configured — skipping.")
            return False
        requests.post(CFG.slack_webhook, json={"text": text}, timeout=10).raise_for_status()
        log.info("Slack notification sent.")
        return True

    def notify_all(self, topic: str, analysis: dict, report_path: Path, emails: list[str]) -> None:
        self.send_email(
            to      = emails,
            subject = f"[AI Report] {topic} — {datetime.now():%d %b %Y}",
            html    = report_path.read_text(encoding="utf-8"),
        )
        insights = "\n".join(f"  • {i}" for i in analysis.get("key_insights", []))
        self.send_slack(
            f"*📊 AI Report: {topic}*\n"
            f"Sentiment: *{analysis.get('sentiment','?')}*\n\n"
            f"*Summary:* {analysis.get('executive_summary','')}\n\n"
            f"*Key Insights:*\n{insights}\n\n"
            f"*Action:* {analysis.get('recommended_action','')}\n"
            f"Report: `{report_path}`"
        )


# ══════════════════════════════════════════════════════════════
#  MODULE 5: PIPELINE ORCHESTRATOR
# ══════════════════════════════════════════════════════════════
class AutomationPipeline:
    """
    Top-level orchestrator.

    Usage
    ─────
    pipeline = AutomationPipeline(
        topic      = "AI & Machine Learning",
        source_url = "https://techcrunch.com/category/artificial-intelligence/",
        emails     = ["you@example.com"],
    )
    pipeline.run()                    # one shot
    pipeline.schedule(interval_hours=24)  # recurring (blocks)
    """

    def __init__(self, topic: str, source_url: str, emails: Optional[list[str]] = None):
        self.topic      = topic
        self.source_url = source_url
        self.emails     = emails or []

        self.collector = DataCollector()
        self.analyser  = AIAnalyser()
        self.reporter  = ReportGenerator()
        self.notifier  = Notifier()

    @timed
    def run(self) -> dict[str, Any]:
        border = "═" * 56
        log.info(border)
        log.info("  PIPELINE START  |  topic: %s", self.topic)
        log.info(border)

        # 1. Collect
        log.info("Step 1/4 — Collecting")
        articles = self.collector.collect(self.source_url)
        if not articles:
            log.error("No articles — aborting.")
            return {"status": "failed", "reason": "no_articles"}

        # 2. Analyse
        log.info("Step 2/4 — AI analysis")
        analysis = self.analyser.analyse(articles, topic=self.topic)

        # 3. Report
        log.info("Step 3/4 — Generating report")
        report_path = self.reporter.save(self.topic, analysis, articles)

        # 4. Notify
        log.info("Step 4/4 — Notifications")
        if self.emails:
            self.notifier.notify_all(self.topic, analysis, report_path, self.emails)

        log.info(border)
        log.info("  PIPELINE DONE")
        log.info(border)

        return {
            "status":      "success",
            "articles":    len(articles),
            "analysis":    analysis,
            "report_path": str(report_path),
        }

    def schedule(self, interval_hours: int = 24) -> None:
        """Run immediately, then repeat every interval_hours hours."""
        log.info("Scheduler active — running every %dh", interval_hours)
        self.run()
        schedule.every(interval_hours).hours.do(self.run)
        while True:
            schedule.run_pending()
            time.sleep(60)


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":

    pipeline = AutomationPipeline(
        topic      = "Artificial Intelligence & Automation",
        source_url = "https://techcrunch.com/category/artificial-intelligence/",
        emails     = [],   # add "you@example.com" to receive email reports
    )

    # One-shot run
    result = pipeline.run()
    print(json.dumps(result, indent=2, default=str))

    # Uncomment to run every 24 hours automatically:
    # pipeline.schedule(interval_hours=24)
