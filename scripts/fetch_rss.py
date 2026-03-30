#!/usr/bin/env python3
"""
RSS収集スクリプト（安定化版）
- タイムアウト/リトライ機能
- 部分失敗許容（1ソース失敗しても継続）
- news.json自動ローテーション（最新500件保持）
- 重複検出強化（URL正規化）
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

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
NEWS_PATH = DATA_DIR / "news.json"

# 設定
MAX_ITEMS = 500  # news.jsonに保持する最大件数
TIMEOUT = 15  # 各RSS取得のタイムアウト（秒）
MAX_RETRIES = 3  # リトライ回数

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
        backoff_factor=1,  # 1秒, 2秒, 4秒...
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def normalize_url(url: str) -> str:
    """URL正規化（重複検出精度向上）"""
    try:
        parsed = urlparse(url)
        # クエリパラメータをソート・断片削除
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            ""  # fragment削除
        ))
        return normalized
    except:
        return url

def fetch_feed(source: dict, session: requests.Session) -> list:
    """単一RSSフィード取得（エラー耐性付き）"""
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
        
        for entry in feed.entries[:30]:  # 最新30件
            # タイトル・リンク必須
            if not entry.get("title") or not entry.get("link"):
                continue
            
            item = {
                "title": entry.title.strip(),
                "link": normalize_url(entry.link),
                "source": source["name"],
                "category": source["category"],
                "language": source["language"],
                "date": entry.get("published", entry.get("updated", "")),
                "summary": entry.get("summary", "")[:300],
            }
            
            # セキュリティスコア推定（CVSSベース）
            if "cvss" in entry.get("summary", "").lower():
                try:
                    # 簡易抽出: "CVSS 8.5" などを検出
                    import re
                    match = re.search(r"cvss[:\s]+(\d+\.?\d*)", entry.get("summary", ""), re.I)
                    if match:
                        item["score"] = float(match.group(1))
                        if item["score"] >= 9.0:
                            item["severity"] = "critical"
                        elif item["score"] >= 7.0:
                            item["severity"] = "high"
                        elif item["score"] >= 4.0:
                            item["severity"] = "medium"
                except:
                    pass
            
            items.append(item)
        
        print(f"✓ {len(items)} items")
        
    except requests.Timeout:
        print(f"✗ Timeout (>{TIMEOUT}s)")
    except requests.RequestException as e:
        print(f"✗ Network error: {e}")
    except Exception as e:
        print(f"✗ Parse error: {e}")
    
    return items

def deduplicate_items(new_items: list, existing_items: list) -> list:
    """重複除去（URL正規化ベース）"""
    existing_urls = {normalize_url(i["link"]) for i in existing_items}
    unique = []
    for item in new_items:
        norm_url = normalize_url(item["link"])
        if norm_url not in existing_urls:
            unique.append(item)
            existing_urls.add(norm_url)
    return unique

def rotate_news_json(items: list, max_items: int) -> list:
    """news.jsonローテーション（最新N件保持）"""
    if len(items) <= max_items:
        return items
    
    # 日付でソート（新→古）
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
    
    # RSS収集（並列ではなく順次：安定性重視）
    session = create_session()
    all_new_items = []
    
    for source in SOURCES:
        items = fetch_feed(source, session)
        all_new_items.extend(items)
        time.sleep(0.5)  # レート制限対策
    
    # 重複除去
    unique_items = deduplicate_items(all_new_items, existing_items)
    print(f"New unique items: {len(unique_items)}")
    
    # 既存データと統合
    merged_items = unique_items + existing_items
    
    # ローテーション
    final_items = rotate_news_json(merged_items, MAX_ITEMS)
    
    # 保存
    output_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "items": final_items
    }
    
    with open(NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Saved: {NEWS_PATH} ({len(final_items)} items)")

if __name__ == "__main__":
    main()
