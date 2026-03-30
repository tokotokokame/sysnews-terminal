#!/usr/bin/env python3
"""
月次アーカイブ生成スクリプト（安定化版・パス修正）
- 記事0件でもJSON生成
- 古い月のgzip圧縮（3ヶ月以上前）
- score文字列を安全にfloatキャスト
- parse_dt例外時は現在時刻を返す
"""
import json
import gzip
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from dateutil import parser

# パス解決を修正（スクリプトの親ディレクトリをベースに）
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent  # sysnews-terminal/
DATA_DIR = REPO_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# 3ヶ月より古い月はgzip圧縮
COMPRESS_MONTHS_AGO = 3

def parse_dt(s: str) -> datetime:
    """日付文字列を安全にパース"""
    try:
        dt = parser.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return datetime.now(timezone.utc)

def safe_float(val, default=0.0) -> float:
    """scoreを安全にfloatキャスト"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def compress_old_archives(compress_before: datetime):
    """古い月のアーカイブをgzip圧縮"""
    compressed_count = 0
    for json_path in ARCHIVE_DIR.glob("*.json"):
        if json_path.name == "index.json":
            continue
        
        # 月文字列からdatetime生成
        try:
            month_str = json_path.stem  # "2025-12"
            month_dt = datetime.strptime(month_str, "%Y-%m").replace(tzinfo=timezone.utc)
            
            if month_dt < compress_before:
                # gzip圧縮
                gz_path = json_path.with_suffix(".json.gz")
                if not gz_path.exists():
                    with open(json_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            f_out.writelines(f_in)
                    
                    # 元ファイル削除
                    json_path.unlink()
                    compressed_count += 1
                    print(f"🗜️  Compressed: {json_path.name} → {gz_path.name}")
        except:
            pass
    
    if compressed_count > 0:
        print(f"✅ Compressed {compressed_count} old archives")

def main():
    news_path = DATA_DIR / "news.json"
    if not news_path.exists():
        print(f"❌ news.json not found at {news_path}")
        return

    with open(news_path, encoding="utf-8") as f:
        data = json.load(f)
    
    items = data.get("items", [])
    if not items:
        print("❌ No items in news.json")
        return

    print(f"📊 Processing {len(items)} items...")

    # 月の範囲を自動生成
    dates = [parse_dt(i.get("date", "")) for i in items if i.get("date")]
    if not dates:
        print("❌ No valid dates found")
        return

    min_month = min(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    max_month = max(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current = min_month
    while current <= max_month:
        # 次月の1日
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1)
        else:
            next_month = current.replace(month=current.month+1)

        month_str = current.strftime("%Y-%m")
        
        # 該当月の記事抽出
        month_items = [
            i for i in items
            if current <= parse_dt(i.get("date", "")) < next_month
        ]

        # ★修正: 記事0件でもJSONを生成
        
        # ソース別集計
        source_counts = Counter(i.get("source", "") for i in month_items)
        
        # 重要度別集計（severity フィールドがあれば）
        sev_counts = Counter(
            i.get("severity", "") for i in month_items if i.get("severity")
        )
        
        # Top記事（scoreが高い順）
        top_articles = sorted(
            [i for i in month_items if i.get("score")],
            key=lambda x: -safe_float(x.get("score", 0))
        )[:20]
        
        # セキュリティハイライト（severity フィールドがあれば）
        security_items = sorted(
            [i for i in month_items if i.get("severity") in ("critical", "high")],
            key=lambda x: parse_dt(x.get("date", "")),
            reverse=True
        )[:30]

        # 月次アーカイブJSON生成
        archive_data = {
            "month": month_str,
            "total_articles": len(month_items),
            "source_counts": dict(source_counts),
            "severity_counts": dict(sev_counts),
            "top_articles": top_articles,
            "security_highlights": security_items
        }

        out_path = ARCHIVE_DIR / f"{month_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)
        
        print(f"📅 Generated: {month_str}.json ({len(month_items)} articles)")
        
        current = next_month

    # 古いアーカイブをgzip圧縮
    compress_before = datetime.now(timezone.utc) - timedelta(days=30*COMPRESS_MONTHS_AGO)
    compress_old_archives(compress_before)

    # index.json生成（.json と .json.gz の両方を含む）
    archive_files = []
    
    # 通常JSON
    for fpath in ARCHIVE_DIR.glob("*.json"):
        if fpath.name == "index.json":
            continue
        with open(fpath, encoding="utf-8") as f:
            arch = json.load(f)
        archive_files.append({
            "month": arch["month"],
            "total_articles": arch["total_articles"],
            "file": fpath.name,
            "compressed": False
        })
    
    # gzip圧縮JSON
    for fpath in ARCHIVE_DIR.glob("*.json.gz"):
        with gzip.open(fpath, "rt", encoding="utf-8") as f:
            arch = json.load(f)
        archive_files.append({
            "month": arch["month"],
            "total_articles": arch["total_articles"],
            "file": fpath.name,
            "compressed": True
        })
    
    # 月降順ソート
    archive_files.sort(key=lambda x: x["month"], reverse=True)

    index_data = {"months": archive_files}
    index_path = ARCHIVE_DIR / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Generated: index.json ({len(archive_files)} months)")
    print(f"📂 Archive directory: {ARCHIVE_DIR}")

if __name__ == "__main__":
    main()
