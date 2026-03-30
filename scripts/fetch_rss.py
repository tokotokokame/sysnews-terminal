#!/usr/bin/env python3
"""
RSS収集スクリプト（高品質ソース厳選版）
- 完全日本語翻訳（deep-translator）
- 信頼性の高いメディア・公式ソースのみ
- タイムアウト/リトライ機能
- 部分失敗許容
"""
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from deep_translator import GoogleTranslator

# パス解決
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
NEWS_PATH = DATA_DIR / "news.json"

# 設定
MAX_ITEMS = 500
TIMEOUT = 15
MAX_RETRIES = 3

# 翻訳インスタンス
translator = GoogleTranslator(source='auto', target='ja')

# ========================================
# 高品質RSSソース（厳選）
# ========================================
SOURCES = [
    # ── セキュリティ（公式・専門メディア）────────────────────
    {
        "name": "The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Krebs on Security",
        "url": "https://krebsonsecurity.com/feed/",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Bleeping Computer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Dark Reading",
        "url": "https://www.darkreading.com/rss.xml",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "SecurityWeek",
        "url": "https://www.securityweek.com/feed/",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Threatpost",
        "url": "https://threatpost.com/feed/",
        "category": "security",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "NVD - CVE (公式)",
        "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss-analyzed.xml",
        "category": "security",
        "language": "en",
        "quality": "official"
    },
    {
        "name": "Exploit Database",
        "url": "https://www.exploit-db.com/rss.xml",
        "category": "security",
        "language": "en",
        "quality": "official"
    },
    {
        "name": "JPCERT/CC (日本公式)",
        "url": "https://www.jpcert.or.jp/rss/jpcert.rdf",
        "category": "security",
        "language": "ja",
        "quality": "official"
    },
    {
        "name": "IPA 情報処理推進機構",
        "url": "https://www.ipa.go.jp/security/announce/alert.rdf",
        "category": "security",
        "language": "ja",
        "quality": "official"
    },
    
    # ── 技術ニュース（大手メディア）──────────────────────
    {
        "name": "Hacker News",
        "url": "https://news.ycombinator.com/rss",
        "category": "tech",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "tech",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "category": "tech",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "category": "tech",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Wired",
        "url": "https://www.wired.com/feed/rss",
        "category": "tech",
        "language": "en",
        "quality": "high"
    },
    
    # ── AI・機械学習（専門メディア）───────────────────────
    {
        "name": "MIT Technology Review - AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "category": "ai",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "VentureBeat - AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "category": "ai",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "AI News",
        "url": "https://www.artificialintelligence-news.com/feed/",
        "category": "ai",
        "language": "en",
        "quality": "high"
    },
    
    # ── ペンテスト・レッドチーム──────────────────────────
    {
        "name": "Offensive Security Blog",
        "url": "https://www.offensive-security.com/blog/feed/",
        "category": "pentest",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "PortSwigger Blog",
        "url": "https://portswigger.net/blog/rss",
        "category": "pentest",
        "language": "en",
        "quality": "high"
    },
    {
        "name": "Pentest Blog",
        "url": "https://pentest.blog/feed/",
        "category": "pentest",
        "language": "en",
        "quality": "high"
    },
]

def create_session() -> requests.Session:
    """リトライ機能付きセッション作成"""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def normalize_url(url: str) -> str:
    """URL正規化"""
    try:
        parsed = urlparse(url)
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            ""
        ))
        return normalized
    except:
        return url

def translate_text(text: str, source_lang: str) -> str:
    """テキスト翻訳"""
    if not text or not text.strip():
        return text
    
    if source_lang == 'ja':
        return text
    
    try:
        if len(text) > 5000:
            text = text[:5000]
        
        translated = translator.translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"    ⚠️  Translation failed: {e}")
        return text

def fetch_feed(source: dict, session: requests.Session) -> list:
    """単一RSSフィード取得"""
    items = []
    try:
        print(f"Fetching: {source['name']} [{source['quality']}] ...", end=" ", flush=True)
        response = session.get(
            source["url"],
            timeout=TIMEOUT,
            headers={"User-Agent": "SE-NEWS/1.0"}
        )
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        
        for entry in feed.entries[:30]:
            if not entry.get("title") or not entry.get("link"):
                continue
            
            title = entry.title.strip()
            summary = entry.get("summary", "")[:300]
            
            # 翻訳実行
            title_ja = translate_text(title, source["language"])
            summary_ja = translate_text(summary, source["language"]) if summary else ""
            
            item = {
                "title": title,
                "title_ja": title_ja,
                "link": normalize_url(entry.link),
                "source": source["name"],
                "category": source["category"],
                "quality": source["quality"],
                "language": source["language"],
                "date": entry.get("published", entry.get("updated", "")),
                "summary": summary,
                "summary_ja": summary_ja,
            }
            
            items.append(item)
            time.sleep(0.1)
        
        print(f"✓ {len(items)} items")
        
    except requests.Timeout:
        print(f"✗ Timeout")
    except requests.RequestException as e:
        print(f"✗ Error: {str(e)[:50]}")
    except Exception as e:
        print(f"✗ Error: {str(e)[:50]}")
    
    return items

def deduplicate_items(new_items: list, existing_items: list) -> list:
    """重複除去"""
    # 既存データが 'link' と 'url' のどちらのキーを持っていても対応可能にする
    existing_urls = {normalize_url(i.get("link", i.get("url", ""))) for i in existing_items if i.get("link") or i.get("url")}
    unique = []
    for item in new_items:
        norm_url = normalize_url(item.get("link", item.get("url", "")))
        if norm_url and norm_url not in existing_urls:
            unique.append(item)
            existing_urls.add(norm_url)
    return unique
    
def rotate_news_json(items: list, max_items: int) -> list:
    """news.jsonローテーション"""
    if len(items) <= max_items:
        return items
    
    sorted_items = sorted(
        items,
        key=lambda x: x.get("date", ""),
        reverse=True
    )
    
    rotated = sorted_items[:max_items]
    print(f"🔄 Rotated: {len(items)} → {len(rotated)} items")
    return rotated

def main():
    # 既存データ読み込み
    if NEWS_PATH.exists():
        with open(NEWS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        existing_items = data.get("items", [])
    else:
        existing_items = []
    
    print(f"📰 SE/NEWS RSS Collector (High-Quality Sources)")
    print(f"Existing items: {len(existing_items)}")
    print(f"Sources: {len(SOURCES)}")
    print("")
    
    # RSS収集
    session = create_session()
    all_new_items = []
    
    for source in SOURCES:
        items = fetch_feed(source, session)
        all_new_items.extend(items)
        time.sleep(0.5)
    
    print("")
    
    # 重複除去
    unique_items = deduplicate_items(all_new_items, existing_items)
    print(f"✨ New unique items: {len(unique_items)}")
    
    # 既存データと統合
    merged_items = unique_items + existing_items
    
    # ローテーション
    final_items = rotate_news_json(merged_items, MAX_ITEMS)
    
    # 品質別統計
    quality_stats = {}
    for item in final_items:
        q = item.get("quality", "unknown")
        quality_stats[q] = quality_stats.get(q, 0) + 1
    
    print(f"📊 Quality distribution: {quality_stats}")
    
    # 保存
    output_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(final_items),
        "items": final_items
    }
    
    with open(NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Saved: {NEWS_PATH} ({len(final_items)} items)")

if __name__ == "__main__":
    main()
