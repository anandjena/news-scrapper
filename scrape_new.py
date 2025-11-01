#!/usr/bin/env python3
"""
scrape_today_news.py
Scrapes today's articles from:
The Hindu, Hindustan Times, Times Now, India Today, Republic World, The Print, The Wire, NDTV

Outputs CSV: news_YYYY-MM-DD.csv (date = today in Asia/Kolkata)
"""

import requests
from bs4 import BeautifulSoup
from newspaper import Article, Config
import csv
import time
import datetime
from dateutil import parser
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
import feedparser
import re
import json

# ---- Config ----
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 1.0  # seconds
MAX_LINKS_PER_SITE = 250

# newspaper3k config
config = Config()
config.browser_user_agent = USER_AGENT
config.request_timeout = REQUEST_TIMEOUT

# timezone for "today"
IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()
FILENAME = f"news_{today_ist.isoformat()}.csv"

# Sites and seed pages
SITES = {
    "The Hindu": [
        "https://www.thehindu.com/",
        "https://www.thehindu.com/archive/",
    ],
    "India Today": [
        "https://www.indiatoday.in/",
    ],
    
    "Indian Express": [
        "https://indianexpress.com/",
        "https://indianexpress.com/feed/"
    ],
    
    "Hindustan Times": [
        "https://www.hindustantimes.com/",
        "https://www.hindustantimes.com/feeds/",
    ],
    "Times Now": [
        "https://www.timesnownews.com/",
    ],
    
    "Republic World": [
        "https://www.republicworld.com/",
    ],
    "The Print": [
        "https://theprint.in/",
    ],
    "The Wire": [
        "https://m.thewire.in/"
    ]
}

# ---- Helper functions ----
def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return r.text
    except Exception as e:
        print(f"  [fetch error] {url} -> {e}")
        return None


def extract_category_from_url(url):
    """Guess article category from its URL path."""
    path = urlparse(url).path.lower()
    categories = [
        "politics", "economy", "business", "world", "india", "sports",
        "entertainment", "science", "tech", "technology", "education",
        "lifestyle", "health", "law", "rights", "society", "culture",
        "gender", "media", "opinion"
    ]
    for cat in categories:
        if f"/{cat}/" in path:
            return cat.capitalize()
    return ""


def is_valid_thewire_article(url):
    if 'thewire.in' not in url:
        return False

    skip_patterns = [
        '/author/', '/tag/', '/category/', '/page/',
        '/about', '/contact', '/privacy', '/terms',
        '.jpg', '.png', '.gif', '.pdf', '#',
        '/wp-content/', '/wp-admin/', '/feed',
        'facebook.com', 'twitter.com', 'instagram.com',
        '/search/', '/subscribe/', '/newsletter/'
    ]
    for pattern in skip_patterns:
        if pattern in url.lower():
            return False

    article_indicators = [
        '/politics/', '/economy/', '/society/', '/world/',
        '/law/', '/rights/', '/security/', '/diplomacy/',
        '/article/', '/news/', '/opinion/', '/external-affairs/',
        '/science/', '/culture/', '/gender/', '/media/'
    ]
    return any(indicator in url.lower() for indicator in article_indicators)


def extract_date_from_thewire_url(url):
    date_pattern = r'/(\d{4})/(\d{2})/(\d{2})/'
    match = re.search(date_pattern, url)
    if match:
        year, month, day = match.groups()
        try:
            return datetime.date(int(year), int(month), int(day))
        except ValueError:
            pass
    return None


def collect_candidate_links(base_url, html):
    links = set()
    if not html:
        return links

    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc

    if 'thewire.in' in base_domain:
        selectors = [
            'article a[href]',
            '.post-title a[href]',
            '.entry-title a[href]',
            'h1 a[href]',
            'h2 a[href]',
            'h3 a[href]',
            '.article-title a[href]',
            '.story-card a[href]',
            '.featured-story a[href]',
            'a[href*="/politics/"]',
            'a[href*="/economy/"]',
            'a[href*="/society/"]',
            'a[href*="/world/"]',
            'a[href*="/law/"]',
            'a[href*="/rights/"]',
            'a[href*="/security/"]',
            'a[href*="/diplomacy/"]',
            'a[href*="/external-affairs/"]',
            'a[href*="/science/"]',
            'a[href*="/culture/"]',
            'a[href*="/gender/"]',
            'a[href*="/media/"]'
        ]
        for selector in selectors:
            for a in soup.select(selector):
                href = a.get('href', '').strip()
                if href and not href.startswith('#') and not href.startswith('mailto:'):
                    full_url = urljoin(base_url, href)
                    if is_valid_thewire_article(full_url):
                        links.add(full_url.split("?")[0].rstrip("/"))
    else:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            href = urljoin(base_url, href)
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc.endswith(base_domain):
                links.add(href.split("?")[0].rstrip("/"))
    return links


def extract_thewire_article(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        article_data = {
            "url": url,
            "title": "",
            "authors": [],
            "summary": "",
            "text": "",
            "publish_date": None,
            "category": "",
        }

        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'NewsArticle':
                    if not article_data['title'] and 'headline' in data:
                        article_data['title'] = data['headline'].replace(' - The Wire', '').strip()

                    if not article_data['publish_date'] and 'datePublished' in data:
                        pub_date = parser.parse(data['datePublished'])
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=datetime.timezone.utc).astimezone(IST)
                        else:
                            pub_date = pub_date.astimezone(IST)
                        article_data['publish_date'] = pub_date

                    if not article_data['text'] and 'articleBody' in data:
                        article_data['text'] = data['articleBody']
                        article_data['summary'] = data['articleBody'][:200] + "..." if len(data['articleBody']) > 200 else data['articleBody']

                    if not article_data['authors'] and 'author' in data:
                        author_info = data['author']
                        if isinstance(author_info, dict) and 'name' in author_info:
                            article_data['authors'] = [author_info['name']]
                        elif isinstance(author_info, list):
                            authors = [a['name'] for a in author_info if isinstance(a, dict) and 'name' in a]
                            article_data['authors'] = authors
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        if not article_data['title']:
            title_meta = soup.find('meta', property='og:title')
            if title_meta:
                article_data['title'] = title_meta.get('content', '').replace(' - The Wire', '').strip()
            else:
                h1 = soup.find('h1')
                if h1:
                    article_data['title'] = h1.get_text(strip=True)

        if not article_data['publish_date']:
            date_meta = soup.find('meta', attrs={'name': 'article:published_date'})
            if date_meta:
                pub_date = parser.parse(date_meta.get('content'))
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=datetime.timezone.utc).astimezone(IST)
                else:
                    pub_date = pub_date.astimezone(IST)
                article_data['publish_date'] = pub_date

        if not article_data['summary']:
            desc_meta = soup.find('meta', property='og:description')
            if desc_meta:
                article_data['summary'] = desc_meta.get('content', '').strip()

        # ---- Category extraction ----
        cat_meta = soup.find("meta", property="article:section")
        if cat_meta and cat_meta.get("content"):
            article_data["category"] = cat_meta["content"].strip()
        else:
            article_data["category"] = extract_category_from_url(url)

        if not article_data['text']:
            content_selectors = [
                '.entry-content', '.post-content', '.article-content', '.content', 'article .text', '.post-body'
            ]
            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    for unwanted in elem.select('script, style, .advertisement, .social-share, .related-articles'):
                        unwanted.decompose()
                    paragraphs = [p.get_text(strip=True) for p in elem.find_all(['p', 'div']) if len(p.get_text(strip=True)) > 20]
                    if paragraphs:
                        article_data['text'] = ' '.join(paragraphs)
                        if not article_data['summary']:
                            article_data['summary'] = paragraphs[0][:200] + "..." if len(paragraphs[0]) > 200 else paragraphs[0]
                    break
        return article_data
    except Exception as e:
        print(f"    [thewire parse failed] {url} -> {e}")
        return None


def extract_article_with_newspaper(url):
    if 'thewire.in' in url:
        return extract_thewire_article(url)
    art = Article(url, config=config)
    try:
        art.download()
        art.parse()
    except Exception as e:
        print(f"    [newspaper parse failed] {url} -> {e}")
        return None
    try:
        art.nlp()
        summary = art.summary
    except Exception:
        summary = ""
    pub_date = None
    if art.publish_date:
        pub_date = art.publish_date
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=datetime.timezone.utc).astimezone(IST)
        else:
            pub_date = pub_date.astimezone(IST)
    category = extract_category_from_url(url)
    return {
        "url": url,
        "title": art.title or "",
        "authors": art.authors or [],
        "summary": summary or "",
        "text": art.text or "",
        "publish_date": pub_date,
        "category": category,
    }


def scrape_ndtv_rss():
    print("\n==> Scraping NDTV via RSS feed")
    feed = feedparser.parse("https://feeds.feedburner.com/ndtvnews-top-stories")
    results = []
    for entry in feed.entries:
        if not hasattr(entry, "published"):
            continue
        try:
            pub_date = parser.parse(entry.published).astimezone(IST).date()
        except Exception:
            continue
        if pub_date == today_ist:
            article_data = {
                "site": "NDTV",
                "url": entry.link,
                "title": entry.title,
                "authors": "",
                "summary": entry.get("summary", ""),
                "text": "",
                "publish_date": entry.published,
                "category": extract_category_from_url(entry.link),
            }


            try:
                article = Article(entry.link)
                article.download()
                article.parse()
                article_data["text"] = article.text
                article_data["authors"] = ", ".join(article.authors)
            except Exception as e:
                print(f"Error extracting {entry.link}: {e}")

            results.append(article_data)
    print(f"  {len(results)} articles kept for NDTV (RSS)")
    return results


def scrape_site(site_name, seed_pages):
    print(f"\n==> Scraping {site_name}")
    candidate_links = set()
    for seed in seed_pages:
        print(f"  fetching seed: {seed}")
        html = fetch(seed)
        if not html:
            continue
        new_links = collect_candidate_links(seed, html)
        print(f"    found {len(new_links)} links on seed")
        candidate_links.update(new_links)
        if len(candidate_links) >= MAX_LINKS_PER_SITE:
            break
    print(f"  total candidate links collected: {len(candidate_links)}")

    results = []
    for count, link in enumerate(list(candidate_links)[:MAX_LINKS_PER_SITE], 1):
        print(f"   [{count}/{min(len(candidate_links), MAX_LINKS_PER_SITE)}] parsing: {link}")
        art = extract_article_with_newspaper(link)
        if not art:
            continue
        pub = art.get("publish_date")
        keep = False
        if pub:
            keep = (pub.date() == today_ist)
        elif 'thewire.in' in link:
            url_date = extract_date_from_thewire_url(link)
            keep = (url_date == today_ist) if url_date else True
        else:
            path = urlparse(link).path
            keep = today_ist.isoformat() in path

        if keep:
            row = {
                "site": site_name,
                "url": art["url"],
                "title": art["title"].strip(),
                "authors": ", ".join(art["authors"]) if isinstance(art["authors"], list) else str(art["authors"]),
                "summary": art["summary"].strip().replace("\n", " "),
                "text": art["text"].strip().replace("\n", " "),
                "publish_date": art["publish_date"].isoformat() if art["publish_date"] else "",
                "category": art.get("category", extract_category_from_url(link)),
            }
            results.append(row)
            print(f"     -> kept ({row['category'] or 'no category'})")
        else:
            print("     -> skipped (not today's article)")
    print(f"  {len(results)} articles kept for {site_name}")
    return results


def main():
    all_rows = []
    all_rows.extend(scrape_ndtv_rss())
    for site, seeds in SITES.items():
        try:
            all_rows.extend(scrape_site(site, seeds))
        except Exception as e:
            print(f"[error scraping site {site}] {e}")

    if not all_rows:
        print("\nNo articles found for today.")
        return

    fieldnames = ["site", "url", "title", "authors", "summary", "text", "publish_date", "category"]
    print(f"\nWriting {len(all_rows)} rows to {FILENAME} ...")
    with open(FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print("Done.")


if __name__ == "__main__":
    main()
