# 🇺🇸 Green Card Priority Date Tracker / 绿卡排期追踪 / Seguimiento de Fecha Prioritaria

**Live site → [zhenwei-shi.github.io/greencard-tracker](https://zhenwei-shi.github.io/greencard-tracker/)**

A free, serverless tool for tracking U.S. green card priority dates. No login, no fees — data is sourced directly from the official [U.S. Department of State Visa Bulletin](https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html) and updated automatically every month via GitHub Actions.

Available in **English**, **中文**, and **Español**.

---

## Features

- **Personal priority date check** — enter your category, country of birth, and priority date to instantly see if you can file
- **Historical trend chart** — visualize month-by-month cutoff date movement with your priority date as a reference line
- **Chart A & Chart B** — toggle between Final Action Dates and Dates for Filing
- **Current bulletin overview** — full table of all EB and family-based categories
- **Auto-updates** — GitHub Actions scrapes the latest Visa Bulletin on the 25th of every month
- **No server, no account** — static site on GitHub Pages; personal settings saved in your browser

---

## Supported Visa Categories

**Employment-Based:** EB-1, EB-2, EB-3, EB-3 (Other Workers), EB-4, EB-5

**Family-Sponsored:** F1, F2A, F2B, F3, F4

**Countries tracked:** China (mainland), India, Mexico, Philippines, All Other Countries (ROW)

---

## How It Works

```
GitHub Actions (runs on the 25th of each month)
    ↓  scrapes travel.state.gov
    ↓  parses Chart A & Chart B tables
    ↓  saves JSON to /data/
GitHub Pages
    ↓  serves static index.html
Browser
    ↓  reads JSON, renders charts & tables
    ↓  saves your settings to localStorage
```

No backend server required.

---

## Run Locally

```bash
# Install dependencies
pip install requests beautifulsoup4

# Fetch latest bulletin
python scraper/scraper.py

# Fetch last 12 months of history
python scraper/scraper.py --history 12

# Open index.html in browser (needs a local server for fetch() to work)
python -m http.server 8000
# then visit http://localhost:8000
```

---

## Manual Data Update

Go to **Actions → Scrape Visa Bulletin → Run workflow** in this repository to trigger an immediate update.

---

## Tests

```bash
cd scraper
pip install pytest
pytest test_scraper.py -v
```

24 unit tests + 1 integration test covering date parsing, country normalization, category mapping, and chart-type detection.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Scraper | Python + BeautifulSoup4 |
| Data | JSON files in `/data/` |
| Frontend | Vanilla HTML/CSS/JS + Chart.js |
| Hosting | GitHub Pages (free) |
| Automation | GitHub Actions (free) |

---

## Data Source

Official U.S. Department of State Visa Bulletin:
[travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html](https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html)

Data is parsed from the HTML tables and stored as JSON. This tool is not affiliated with or endorsed by the U.S. government.

---

## License

MIT
