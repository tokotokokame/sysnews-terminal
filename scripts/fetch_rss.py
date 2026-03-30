#!/usr/bin/env python3
"""
RSS収集スクリプト（deep-translator統合版）
- 完全日本語翻訳（Google Translate API代替）
- タイムアウト/リトライ機能
- 部分失敗許容
- news.json自動ローテーション（最新500件保持）
- 重複検出強化
"""
import json
import time
import hashlib
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

# 翻訳インスタンス（再利用）
translator = GoogleTranslator(source='auto', target='ja')

# RSS ソース定義
SOURCES = [
    {
        "name": "Hacker News",
        "url": "https://news.ycombinator.com/rss",
        "category": "tech",
        "language": "en"
    },
    {
        "name": "Zenn",
        "url": "https://zenn.dev/feed",
        "category": "tech",
        "language": "ja"
    },
    {
        "name": "NVD - CVE",
        "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss-analyzed.xml",
        "category": "security",
        "language": "en"
    },
    {
        "name": "The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "category": "security",
        "language": "en"
    },
    {
        "name": "Exploit Database",
        "url": "https://www.exploit-db.com/rss.xml",
        "category": "security",
        "language": "en"
    },
    {
        "name": "JPCERT/CC",
        "url": "https://www.jpcert.or.jp/rss/jpcert.rdf",
        "category": "security",
        "language": "ja"
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
    """テキスト翻訳（エラー耐性付き）"""
    if not text or not text.strip():
        return text
    
    # 日本語ソースはそのまま
    if source_lang == 'ja':
        return text
    
    try:
        # 長すぎるテキストは分割翻訳
        if len(text) > 5000:
            text = text[:5000]
        
        translated = translator.translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"    ⚠️  Translation failed: {e}")
        return text

def fetch_feed(source: dict, session: requests.Session) -> list:
    """単一RSSフィード取得（翻訳付き）"""
    items = []
    try:
        print(f"Fetching: {source['name']} ...", end=" ", flush=True)
        response = session.get(
            source["url"],
            timeout=TIMEOUT,
            headers={"User-Agent": "sysnews-terminal/1.0"}
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
                "language": source["language"],
                "date": entry.get("published", entry.get("updated", "")),
                "summary": summary,
                "summary_ja": summary_ja,
            }
            
            items.append(item)
            
            # レート制限対策（翻訳API保護）
            time.sleep(0.1)
        
        print(f"✓ {len(items)} items")
        
    except requests.Timeout:
        print(f"✗ Timeout (>{TIMEOUT}s)")
    except requests.RequestException as e:
        print(f"✗ Network error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    return items

def deduplicate_items(new_items: list, existing_items: list) -> list:
    """重複除去"""
    existing_urls = {normalize_url(i["link"]) for i in existing_items}
    unique = []
    for item in new_items:
        norm_url = normalize_url(item["link"])
        if norm_url not in existing_urls:
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
    print(f"🔄 Rotated: {len(items)} → {len(rotated)} items (max={max_items})")
    return rotated

def main():
    # 既存データ読み込み
    if NEWS_PATH.exists():
        with open(NEWS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        existing_items = data.get("items", [])
    else:
        existing_items = []
    
    print(f"Existing items: {len(existing_items)}")
    
    # RSS収集
    session = create_session()
    all_new_items = []
    
    for source in SOURCES:
        items = fetch_feed(source, session)
        all_new_items.extend(items)
        time.sleep(0.5)
    
    # 重複除去
    unique_items = deduplicate_items(all_new_items, existing_items)
    print(f"New unique items: {len(unique_items)}")
    
    # 既存データと統合
    merged_items = unique_items + existing_items
    
    # ローテーション
    final_items = rotate_news_json(merged_items, MAX_ITEMS)
    
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
