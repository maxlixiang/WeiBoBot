import html
import json
import os
from datetime import datetime


ARCHIVE_DIR = "archive"
ARCHIVE_JSONL = os.path.join(ARCHIVE_DIR, "weibo_posts.jsonl")
ARCHIVE_HTML = os.path.join(ARCHIVE_DIR, "index.html")


def archive_weibo_post(uid, author, text, images, link, published=None):
    """保存新微博，并重建可浏览的 HTML 归档页。"""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    record = {
        "uid": str(uid),
        "author": str(author),
        "text": str(text),
        "images": [str(img) for img in images],
        "link": str(link),
        "published": str(published or ""),
        "archived_at": datetime.now().isoformat(timespec="seconds"),
    }
    _append_unique_record(record)
    _write_archive_html(_load_records())


def _append_unique_record(record):
    existing_links = {item.get("link") for item in _load_records()}
    if record["link"] in existing_links:
        return

    with open(ARCHIVE_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_records():
    if not os.path.exists(ARCHIVE_JSONL):
        return []

    records = []
    with open(ARCHIVE_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"读取微博归档记录失败: {e}")
    return records


def _write_archive_html(records):
    newest_first = list(reversed(records))
    cards = "\n".join(_render_card(record) for record in newest_first)
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>微博监控归档</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #20242a;
    }}
    body {{
      margin: 0;
      padding: 32px 16px;
    }}
    main {{
      max-width: 920px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .meta {{
      color: #68717d;
      font-size: 14px;
    }}
    article {{
      background: #fff;
      border: 1px solid #e4e7eb;
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .post-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
      color: #68717d;
      font-size: 14px;
    }}
    .author {{
      color: #111827;
      font-weight: 700;
    }}
    .text {{
      white-space: pre-wrap;
      line-height: 1.65;
      margin-bottom: 14px;
    }}
    .images {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 8px;
      margin: 14px 0;
    }}
    .images img {{
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid #e4e7eb;
    }}
    a {{
      color: #1565c0;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>微博监控归档</h1>
      <div class="meta">共 {len(records)} 条记录，最后生成于 {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</div>
    </header>
    {cards or '<p class="meta">暂无归档记录。</p>'}
  </main>
</body>
</html>
"""
    with open(ARCHIVE_HTML, "w", encoding="utf-8") as f:
        f.write(html_text)


def _render_card(record):
    author = html.escape(record.get("author", "未知博主"))
    uid = html.escape(record.get("uid", ""))
    text = html.escape(record.get("text", ""))
    link = html.escape(record.get("link", ""), quote=True)
    published = html.escape(record.get("published") or "未知发布时间")
    archived_at = html.escape(record.get("archived_at", ""))
    images = record.get("images", [])
    image_html = ""
    if images:
        image_html = '<div class="images">' + "".join(
            f'<a href="{html.escape(img, quote=True)}" target="_blank" rel="noreferrer"><img src="{html.escape(img, quote=True)}" loading="lazy" alt=""></a>'
            for img in images
        ) + "</div>"

    return f"""<article>
  <div class="post-head">
    <div><span class="author">{author}</span> <span>({uid})</span></div>
    <div>{published}</div>
  </div>
  <div class="text">{text}</div>
  {image_html}
  <div class="meta">归档：{archived_at} · <a href="{link}" target="_blank" rel="noreferrer">查看原微博</a></div>
</article>"""
