#!/usr/bin/env python3
"""
月次アーカイブ生成スクリプト（要約機能付き）
- 記事0件でもJSON生成
- Top 10記事の要約自動生成
- 古い月のgzip圧縮（3ヶ月以上前）
"""
import json
import gzip
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from dateutil import parser

# パス解決
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

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

def extract_keywords(title: str) -> list:
    """タイトルからキーワード抽出"""
    # 日本語タイトルを優先
    text = title.lower()
    
    # 重要キーワード抽出
    keywords = []
    
    # セキュリティ関連
    security_terms = [
        'セキュリティ', '脆弱性', 'vulnerability', 'security', 'cve', 'exploit',
        'ransomware', 'malware', 'breach', 'hack', 'attack', 'zero-day',
        'ランサムウェア', 'マルウェア', '攻撃', '侵害'
    ]
    
    # AI関連
    ai_terms = [
        'ai', 'gpt', 'llm', 'chatgpt', 'openai', 'anthropic', 'claude',
        'machine learning', 'deep learning', '人工知能', '機械学習', 'モデル'
    ]
    
    # 技術関連
    tech_terms = [
        'python', 'javascript', 'rust', 'go', 'java', 'kubernetes', 'docker',
        'cloud', 'aws', 'azure', 'gcp', 'react', 'vue', 'api', 'framework'
    ]
    
    # 製品名・企業名
    products = [
        'microsoft', 'apple', 'google', 'amazon', 'meta', 'twitter', 'x',
        'github', 'gitlab', 'windows', 'linux', 'macos', 'android', 'ios',
        'chrome', 'firefox', 'safari', 'wordpress', 'apache', 'nginx'
    ]
    
    for term in security_terms + ai_terms + tech_terms + products:
        if term in text:
            keywords.append(term)
    
    return keywords

def generate_monthly_summary(month_items: list, month_str: str) -> str:
    """月次要約を自動生成"""
    if not month_items:
        return f"{month_str}は記事がありませんでした。"
    
    # Top 10記事を取得（scoreがNoneでない記事のみ）
    scored_items = [i for i in month_items if i.get("score") is not None and safe_float(i.get("score", 0)) > 0]
    
    if scored_items:
        top_items = sorted(
            scored_items,
            key=lambda x: -safe_float(x.get("score", 0))
        )[:10]
    else:
        # スコアがない場合は最新10件
        top_items = sorted(
            month_items,
            key=lambda x: parse_dt(x.get("date", "")),
            reverse=True
        )[:10]
    
    if not top_items:
        # スコアがない場合は最新10件
        top_items = sorted(
            month_items,
            key=lambda x: parse_dt(x.get("date", "")),
            reverse=True
        )[:10]
    
    # カテゴリ別集計
    categories = Counter()
    all_keywords = []
    
    for item in top_items:
        # title_jaを優先、なければtitle
        title = item.get("title_ja", item.get("title", ""))
        keywords = extract_keywords(title)
        all_keywords.extend(keywords)
        
        # カテゴリ判定（簡易版）
        text = title.lower()
        if any(k in text for k in ['セキュリティ', 'security', 'vulnerability', 'cve', 'exploit', '脆弱性']):
            categories['security'] += 1
        elif any(k in text for k in ['ai', 'gpt', 'llm', '人工知能', '機械学習']):
            categories['ai'] += 1
        elif any(k in text for k in ['python', 'javascript', 'rust', 'framework', 'プログラミング']):
            categories['tech'] += 1
    
    # 頻出キーワードTop 5
    keyword_counts = Counter(all_keywords)
    top_keywords = [k for k, _ in keyword_counts.most_common(5)]
    
    # 要約文生成
    summary_parts = []
    
    # カテゴリ別の傾向
    if categories:
        dominant_cat = categories.most_common(1)[0][0]
        cat_labels = {
            'security': 'セキュリティ',
            'ai': 'AI・機械学習',
            'tech': '技術・開発'
        }
        dominant_label = cat_labels.get(dominant_cat, '技術')
        summary_parts.append(f"{dominant_label}関連の話題が中心")
    
    # 主要キーワード
    if top_keywords:
        # 日本語化
        keyword_ja = {
            'security': 'セキュリティ', 'vulnerability': '脆弱性',
            'ai': 'AI', 'gpt': 'GPT', 'llm': 'LLM',
            'python': 'Python', 'javascript': 'JavaScript',
            'rust': 'Rust', 'kubernetes': 'Kubernetes',
            'docker': 'Docker', 'cloud': 'クラウド'
        }
        
        keywords_display = [keyword_ja.get(k.lower(), k.title()) for k in top_keywords[:3]]
        summary_parts.append(f"主要トピック: {', '.join(keywords_display)}")
    
    # Top記事のタイトル（最も人気の記事）
    if top_items:
        top_title = top_items[0].get("title_ja", top_items[0].get("title", ""))[:60]
        if len(top_title) == 60:
            top_title += "..."
        summary_parts.append(f"注目: 「{top_title}」")
    
    summary = f"{month_str}の月次まとめ: " + "。".join(summary_parts) + "。"
    
    return summary

def compress_old_archives(compress_before: datetime):
    """古い月のアーカイブをgzip圧縮"""
    compressed_count = 0
    for json_path in ARCHIVE_DIR.glob("*.json"):
        if json_path.name == "index.json":
            continue
        
        try:
            month_str = json_path.stem
            month_dt = datetime.strptime(month_str, "%Y-%m").replace(tzinfo=timezone.utc)
            
            if month_dt < compress_before:
                gz_path = json_path.with_suffix(".json.gz")
                if not gz_path.exists():
                    with open(json_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            f_out.writelines(f_in)
                    
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

        # ソース別集計
        source_counts = Counter(i.get("source", "") for i in month_items)
        
        # 重要度別集計
        sev_counts = Counter(
            i.get("severity", "") for i in month_items if i.get("severity")
        )
        
        # Top記事（scoreがNoneでない記事のみ）
        scored_items = [i for i in month_items if i.get("score") is not None]
        top_articles = sorted(
            scored_items,
            key=lambda x: -safe_float(x.get("score", 0))
        )[:20]
        
        # セキュリティハイライト
        security_items = sorted(
            [i for i in month_items if i.get("severity") in ("critical", "high")],
            key=lambda x: parse_dt(x.get("date", "")),
            reverse=True
        )[:30]

        # 月次要約生成
        summary = generate_monthly_summary(month_items, month_str)

        # 月次アーカイブJSON生成
        archive_data = {
            "month": month_str,
            "total_articles": len(month_items),
            "summary": summary,  # 追加
            "source_counts": dict(source_counts),
            "severity_counts": dict(sev_counts),
            "top_articles": top_articles,
            "security_highlights": security_items
        }

        out_path = ARCHIVE_DIR / f"{month_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)
        
        print(f"📅 Generated: {month_str}.json ({len(month_items)} articles)")
        print(f"   Summary: {summary[:80]}...")
        
        current = next_month

    # 古いアーカイブをgzip圧縮
    compress_before = datetime.now(timezone.utc) - timedelta(days=30*COMPRESS_MONTHS_AGO)
    compress_old_archives(compress_before)

    # index.json生成
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
            "summary": arch.get("summary", ""),  # 追加
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
            "summary": arch.get("summary", ""),  # 追加
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
