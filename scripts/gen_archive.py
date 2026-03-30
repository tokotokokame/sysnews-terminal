#!/usr/bin/env python3
"""
月次アーカイブ生成スクリプト（詳細技術レポート版）
- Top 10記事すべての内容を要約
- カテゴリ別に詳細を列挙
- 技術的な影響・対応を含める
"""
import json
import gzip
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from dateutil import parser

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

COMPRESS_MONTHS_AGO = 3

def parse_dt(s: str) -> datetime:
    try:
        dt = parser.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return datetime.now(timezone.utc)

def safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def extract_detail(summary: str, max_sentences: int = 3) -> str:
    """要約から詳細情報を抽出"""
    if not summary:
        return ""
    
    # 文を分割（。で区切る）
    sentences = summary.replace("。 ", "。").split("。")
    
    # 最初のN文を取得
    detail_sentences = []
    char_count = 0
    
    for sentence in sentences[:max_sentences]:
        sentence = sentence.strip()
        if sentence:
            detail_sentences.append(sentence)
            char_count += len(sentence)
            
            # 200文字程度で打ち切り
            if char_count > 200:
                break
    
    return "。".join(detail_sentences) + ("。" if detail_sentences else "")

def generate_monthly_summary(month_items: list, month_str: str) -> str:
    """詳細技術レポート生成（完全無料）"""
    if not month_items:
        return f"{month_str}は記事がありませんでした。"
    
    # Top 10記事を取得
    scored_items = [i for i in month_items if i.get("score") is not None and safe_float(i.get("score", 0)) > 0]
    
    if scored_items:
        top_items = sorted(scored_items, key=lambda x: -safe_float(x.get("score", 0)))[:10]
    else:
        top_items = sorted(month_items, key=lambda x: parse_dt(x.get("date", "")), reverse=True)[:10]
    
    # カテゴリ別にグループ化
    security_items = []
    ai_items = []
    tech_items = []
    
    for item in top_items:
        title = item.get("title_ja", item.get("title", ""))
        summary = item.get("summary_ja", item.get("summary", ""))
        text = (title + " " + summary).lower()
        
        if any(k in text for k in ["セキュリティ", "security", "vulnerability", "cve", "exploit", "脆弱性", "breach", "attack", "ランサムウェア", "malware"]):
            security_items.append({"title": title, "summary": summary})
        elif any(k in text for k in ["ai", "gpt", "llm", "人工知能", "機械学習", "openai", "anthropic", "claude", "gemini", "chatgpt"]):
            ai_items.append({"title": title, "summary": summary})
        else:
            tech_items.append({"title": title, "summary": summary})
    
    # 詳細レポート生成
    report_parts = []
    
    # ========== セキュリティセクション ==========
    if security_items:
        sec_text = f"**セキュリティ動向 ({len(security_items)}件)**\n\n"
        
        for i, item in enumerate(security_items, 1):
            title = item["title"][:100]
            detail = extract_detail(item["summary"], max_sentences=3)
            
            if detail:
                sec_text += f"{i}. {title}\n   {detail}\n\n"
            else:
                sec_text += f"{i}. {title}\n\n"
        
        report_parts.append(sec_text.strip())
    
    # ========== AIセクション ==========
    if ai_items:
        ai_text = f"**AI・機械学習動向 ({len(ai_items)}件)**\n\n"
        
        for i, item in enumerate(ai_items, 1):
            title = item["title"][:100]
            detail = extract_detail(item["summary"], max_sentences=3)
            
            if detail:
                ai_text += f"{i}. {title}\n   {detail}\n\n"
            else:
                ai_text += f"{i}. {title}\n\n"
        
        report_parts.append(ai_text.strip())
    
    # ========== 技術セクション ==========
    if tech_items:
        tech_text = f"**技術トレンド ({len(tech_items)}件)**\n\n"
        
        for i, item in enumerate(tech_items, 1):
            title = item["title"][:100]
            detail = extract_detail(item["summary"], max_sentences=2)
            
            if detail:
                tech_text += f"{i}. {title}\n   {detail}\n\n"
            else:
                tech_text += f"{i}. {title}\n\n"
        
        report_parts.append(tech_text.strip())
    
    # 最終レポート
    header = f"# {month_str}の技術動向レポート\n\n"
    report = header + "\n\n".join(report_parts)
    
    return report

def generate_html_report(archive_data: dict, month_str: str) -> str:
    """月次HTMLレポート生成（マークダウン対応）"""
    
    # summaryをHTMLに変換（マークダウン風）
    summary = archive_data.get('summary', '今月のまとめ')
    
    # **太字** → <strong>
    summary_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', summary)
    
    # 改行を<br>に変換
    summary_html = summary_html.replace('\n\n', '</p><p>').replace('\n', '<br>')
    
    # # 見出し → <h3>
    summary_html = re.sub(r'^# (.+)$', r'<h2 class="report-title">\1</h2>', summary_html, flags=re.MULTILINE)
    
    # 番号付きリスト: 1. → <li>
    summary_html = re.sub(r'^\d+\.\s+(.+)$', r'<li>\1</li>', summary_html, flags=re.MULTILINE)
    
    # <li>をラップ
    if '<li>' in summary_html:
        summary_html = re.sub(r'(<li>.+?</li>)', r'<ul>\1</ul>', summary_html, flags=re.DOTALL)
    
    # <p>でラップ
    if not summary_html.startswith('<'):
        summary_html = f'<p>{summary_html}</p>'
    
    top_articles = archive_data.get('top_articles', [])[:10]
    top_articles_html = ""
    
    if top_articles:
        top_articles_html = '<div class="section"><h2>🏆 Top 10 人気記事</h2><ul class="top-articles">'
        
        for i, article in enumerate(top_articles, 1):
            rank_class = 'gold' if i == 1 else 'silver' if i == 2 else 'bronze' if i == 3 else ''
            title = article.get('title_ja', article.get('title', ''))
            link = article.get('link', article.get('url', '#'))
            source = article.get('source', '')
            score = article.get('score', 0)
            
            top_articles_html += f'''
        <li>
          <span class="rank {rank_class}">{i}</span>
          <div class="article-title">{title}</div>
          <div class="article-meta">
            📡 {source} | 👍 {score}
            <a href="{link}" target="_blank" class="article-link">記事を読む →</a>
          </div>
        </li>'''
        
        top_articles_html += '</ul></div>'
    
    source_counts = archive_data.get('source_counts', {})
    source_stats_html = ""
    
    if source_counts:
        top_sources = sorted(source_counts.items(), key=lambda x: -x[1])[:10]
        source_stats_html = '<div class="section"><h2>📰 情報源別統計（Top 10）</h2><div class="source-list">'
        
        for source, count in top_sources:
            source_stats_html += f'''
        <div class="source-item">
          <div class="source-name">{source}</div>
          <div class="source-count">{count}</div>
        </div>'''
        
        source_stats_html += '</div></div>'
    
    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{month_str} 月次レポート - SE/NEWS</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', Meiryo, sans-serif; background: #f5f5f5; color: #333; line-height: 1.8; padding: 20px; }}
    .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 20px rgba(0,0,0,0.1); }}
    .header {{ border-bottom: 3px solid #667eea; padding-bottom: 20px; margin-bottom: 30px; }}
    .header h1 {{ font-size: 32px; color: #667eea; margin-bottom: 10px; }}
    .header .meta {{ font-size: 14px; color: #999; }}
    .summary {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; font-size: 15px; line-height: 1.9; }}
    .summary h2 {{ color: white; font-size: 22px; margin-bottom: 15px; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; }}
    .summary strong {{ color: #FFD700; font-weight: 600; }}
    .summary ul {{ margin-left: 20px; margin-top: 10px; }}
    .summary li {{ margin-bottom: 15px; list-style: none; position: relative; padding-left: 25px; }}
    .summary li:before {{ content: "▸"; position: absolute; left: 0; color: #FFD700; font-weight: bold; }}
    .summary p {{ margin-bottom: 15px; }}
    .section {{ margin-bottom: 40px; }}
    .section h2 {{ font-size: 24px; color: #333; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #f0f0f0; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
    .stat-card {{ background: #f8f8f8; padding: 20px; border-radius: 8px; text-align: center; }}
    .stat-card .number {{ font-size: 36px; font-weight: bold; color: #667eea; margin-bottom: 5px; }}
    .stat-card .label {{ font-size: 14px; color: #666; }}
    .top-articles {{ list-style: none; }}
    .top-articles li {{ background: #f8f8f8; padding: 15px; margin-bottom: 10px; border-radius: 8px; border-left: 4px solid #667eea; transition: all 0.2s; }}
    .top-articles li:hover {{ background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); transform: translateX(5px); }}
    .top-articles .rank {{ display: inline-block; width: 30px; height: 30px; background: #667eea; color: white; border-radius: 50%; text-align: center; line-height: 30px; font-weight: bold; margin-right: 10px; }}
    .top-articles .rank.gold {{ background: #FFD700; color: #333; }}
    .top-articles .rank.silver {{ background: #C0C0C0; color: #333; }}
    .top-articles .rank.bronze {{ background: #CD7F32; color: white; }}
    .article-title {{ font-weight: 600; color: #333; font-size: 15px; margin-bottom: 5px; }}
    .article-meta {{ font-size: 12px; color: #999; }}
    .article-link {{ color: #667eea; text-decoration: none; font-size: 12px; }}
    .article-link:hover {{ text-decoration: underline; }}
    .source-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
    .source-item {{ background: #f8f8f8; padding: 15px; border-radius: 8px; }}
    .source-name {{ font-weight: 600; color: #333; margin-bottom: 5px; }}
    .source-count {{ font-size: 24px; color: #667eea; font-weight: bold; }}
    .footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #f0f0f0; text-align: center; color: #999; font-size: 14px; }}
    .back-link {{ display: inline-block; background: #667eea; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; margin-bottom: 20px; }}
    .back-link:hover {{ background: #5568d3; }}
  </style>
</head>
<body>
  <div class="container">
    <a href="../../index.html" class="back-link">← トップページに戻る</a>
    
    <div class="header">
      <h1>📅 {month_str} 月次レポート</h1>
      <div class="meta">SE/NEWS - セキュリティ・テックニュース</div>
    </div>
    
    <div class="summary">
      {summary_html}
    </div>
    
    <div class="section">
      <h2>📊 統計情報</h2>
      <div class="stats">
        <div class="stat-card">
          <div class="number">{archive_data['total_articles']}</div>
          <div class="label">総記事数</div>
        </div>
        <div class="stat-card">
          <div class="number">{len(archive_data.get('source_counts', {}))}</div>
          <div class="label">情報源数</div>
        </div>
        <div class="stat-card">
          <div class="number">{len(top_articles)}</div>
          <div class="label">Top記事</div>
        </div>
      </div>
    </div>
    
    {top_articles_html}
    
    {source_stats_html}
    
    <div class="footer">
      <p>Generated by SE/NEWS</p>
      <p><a href="../../index.html" style="color: #667eea;">トップページに戻る</a></p>
    </div>
  </div>
</body>
</html>'''
    
    return html

def compress_old_archives(compress_before: datetime):
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
        except:
            pass
    
    if compressed_count > 0:
        print(f"✅ Compressed {compressed_count} old archives")

def main():
    news_path = DATA_DIR / "news.json"
    if not news_path.exists():
        print(f"❌ news.json not found")
        return

    with open(news_path, encoding="utf-8") as f:
        data = json.load(f)
    
    items = data.get("items", [])
    if not items:
        print("❌ No items")
        return

    print(f"📊 Processing {len(items)} items...")

    dates = [parse_dt(i.get("date", "")) for i in items if i.get("date")]
    if not dates:
        print("❌ No valid dates")
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
        
        month_items = [i for i in items if current <= parse_dt(i.get("date", "")) < next_month]

        source_counts = Counter(i.get("source", "") for i in month_items)
        sev_counts = Counter(i.get("severity", "") for i in month_items if i.get("severity"))
        
        scored_items = [i for i in month_items if i.get("score") is not None]
        top_articles = sorted(scored_items, key=lambda x: -safe_float(x.get("score", 0)))[:20]
        
        security_items = sorted(
            [i for i in month_items if i.get("severity") in ("critical", "high")],
            key=lambda x: parse_dt(x.get("date", "")),
            reverse=True
        )[:30]

        summary = generate_monthly_summary(month_items, month_str)

        archive_data = {
            "month": month_str,
            "total_articles": len(month_items),
            "summary": summary,
            "source_counts": dict(source_counts),
            "severity_counts": dict(sev_counts),
            "top_articles": top_articles,
            "security_highlights": security_items
        }

        out_path = ARCHIVE_DIR / f"{month_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)
        
        html_content = generate_html_report(archive_data, month_str)
        html_path = ARCHIVE_DIR / f"{month_str}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        print(f"📅 {month_str}: JSON + HTML ({len(month_items)} articles)")
        
        current = next_month

    compress_before = datetime.now(timezone.utc) - timedelta(days=30*COMPRESS_MONTHS_AGO)
    compress_old_archives(compress_before)

    archive_files = []
    
    for fpath in ARCHIVE_DIR.glob("*.json"):
        if fpath.name == "index.json":
            continue
        with open(fpath, encoding="utf-8") as f:
            arch = json.load(f)
        
        month = arch["month"]
        
        archive_files.append({
            "month": month,
            "total_articles": arch["total_articles"],
            "summary": arch.get("summary", ""),
            "file": fpath.name,
            "html_file": f"{month}.html",
            "compressed": False
        })
    
    for fpath in ARCHIVE_DIR.glob("*.json.gz"):
        with gzip.open(fpath, "rt", encoding="utf-8") as f:
            arch = json.load(f)
        
        month = arch["month"]
        
        archive_files.append({
            "month": month,
            "total_articles": arch["total_articles"],
            "summary": arch.get("summary", ""),
            "file": fpath.name,
            "html_file": f"{month}.html",
            "compressed": True
        })
    
    archive_files.sort(key=lambda x: x["month"], reverse=True)

    index_data = {"months": archive_files}
    index_path = ARCHIVE_DIR / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ index.json ({len(archive_files)} months)")

if __name__ == "__main__":
    main()
