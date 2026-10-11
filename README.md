# AI Web Scraping Agent

Claude controls a real browser (Playwright) with tools: `goto`, `get_page_text`, `get_links`,
`click`, `type_text`, `save_records`, `finish`. It decides what to do step by step, then saves
results to `results/*.json` and `*.csv`.

## Setup
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env
```

## 3 ways to trigger it

**1. Command line (manual)**
```bash
python agent.py --goal "Get title and price of all books on first 2 pages" \
  --url https://books.toscrape.com --fields title,price
# add --show-browser to watch it work
```

**2. API (on demand, from any app: website, Zapier, n8n, curl)**
```bash
uvicorn server:app --port 8000
curl -X POST localhost:8000/run -H "Content-Type: application/json" -H "X-API-Key: change-me" \
  -d '{"goal":"Get book titles and prices","start_url":"https://books.toscrape.com","fields":["title","price"]}'
curl localhost:8000/jobs/<job_id> -H "X-API-Key: change-me"
```

**3. Scheduler (automatic)**
Edit `schedules.json`, set `"enabled": true`, and keep `uvicorn server:app` running.
`cron` uses standard format (`0 9 * * *` = daily 9 AM).

## Docker
```bash
docker build -t scraper-agent . && docker run -p 8000:8000 --env-file .env scraper-agent
```

## Safety built in
- Blocks localhost / private-network URLs (SSRF protection)
- Respects robots.txt (toggle with `RESPECT_ROBOTS`)
- Treats page text as untrusted (prompt-injection guard)
- Step limit per job; optional API key on the server

Only scrape sites you are allowed to; check their terms of service. Do not collect personal data
without a lawful basis.
