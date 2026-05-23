
"""
AI 工具情报站 - 每天自动聚合 AI 领域信息源
"""
import html
import os
import re
from datetime import datetime, timedelta, timezone
import feedparser
import requests
FEEDS = {
    "🔥 Product Hunt": "https://www.producthunt.com/feed?category=artificial-intelligence",
    "📰 The Decoder":   "https://the-decoder.com/feed/",
    "📰 VentureBeat AI":"https://venturebeat.com/category/ai/feed/",
    "📰 MIT Tech AI":   "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "🔬 ArXiv AI":      "http://export.arxiv.org/rss/cs.AI",
    "💬 Hacker News":   "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT&count=15",
    "🛠 GitHub Trending":"https://rsshub.app/github/trending/daily/Python",
    "📝 OpenAI Blog":   "https://openai.com/blog/rss.xml",
    "📝 Anthropic":     "https://www.anthropic.com/news/rss.xml",
    "📝 Hugging Face":  "https://huggingface.co/blog/feed.xml",
    "🇨🇳 机器之心":      "https://www.jiqizhixin.com/rss",
    "🇨🇳 量子位":        "https://www.qbitai.com/feed",
}
PER_FEED_LIMIT = 8
TIMEOUT = 15
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
      "Mobile/15E148 Safari/604.1")
def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  fail: {e}")
        return None
def parse_feed(name, url):
    print(f"-> {name}")
    raw = fetch(url)
    if not raw:
        return []
    parsed = feedparser.parse(raw)
    items = []
    for entry in parsed.entries[:PER_FEED_LIMIT]:
        summary = entry.get("summary") or entry.get("description") or ""
        summary = re.sub(r"<[^>]+>", "", summary).strip()[:80]
        items.append({
            "title": (entry.get("title") or "无标题").strip(),
            "link": (entry.get("link") or "#").strip(),
            "source": name,
            "summary": summary,
        })
    print(f"  ok: {len(items)}")
    return items
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#eef2ff" media="(prefers-color-scheme: light)">
<title>🤖 AI 工具情报站</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🤖%3C/text%3E%3C/svg%3E">
<style>
:root {
  --bg: #f5f7fb;
  --bg-grad: radial-gradient(1200px 600px at 50% -200px, #c7d2fe 0%, transparent 60%),
             radial-gradient(800px 400px at 100% 100px, #fbcfe8 0%, transparent 60%),
             #f5f7fb;
  --card: rgba(255, 255, 255, 0.72);
  --text: #0f172a;
  --text-2: #334155;
  --muted: #64748b;
  --accent: #2563eb;
  --accent-2: #7c3aed;
  --border: rgba(15, 23, 42, 0.08);
  --shadow: 0 8px 32px rgba(15, 23, 42, 0.06);
  --blur: blur(20px) saturate(180%);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1220;
    --bg-grad: radial-gradient(1200px 600px at 50% -200px, #3730a3 0%, transparent 60%),
               radial-gradient(800px 400px at 100% 100px, #831843 0%, transparent 60%),
               #0b1220;
    --card: rgba(30, 41, 59, 0.6);
    --text: #f8fafc;
    --text-2: #cbd5e1;
    --muted: #94a3b8;
    --accent: #818cf8;
    --accent-2: #f0abfc;
    --border: rgba(255, 255, 255, 0.08);
    --shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
html { font-size: 18px; scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  background-image: var(--bg-grad);
  background-attachment: fixed;
  color: var(--text);
  line-height: 1.5;
  padding: max(env(safe-area-inset-top), 16px) 14px calc(env(safe-area-inset-bottom) + 80px);
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}
.wrapper { max-width: 760px; margin: 0 auto; }
header { text-align: center; padding: 28px 12px 24px; }
header h1 {
  font-size: 1.7rem;
  font-weight: 900;
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
header .subtitle { font-size: 1.05rem; color: var(--muted); margin-top: 12px; font-weight: 500; }
.stats {
  display: inline-flex; align-items: center; gap: 14px; margin-top: 18px;
  font-size: 0.9rem; color: var(--text-2);
  background: var(--card); backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  padding: 10px 20px; border-radius: 999px;
  border: 1px solid var(--border); box-shadow: var(--shadow);
}
.stats b { color: var(--accent); font-weight: 800; font-size: 1.05rem; }
.stats .dot { width: 4px; height: 4px; background: var(--muted); border-radius: 50%; }
.search-bar { position: sticky; top: 8px; z-index: 50; margin: 20px 0 24px; }
.search-bar input {
  width: 100%; font-size: 1.05rem; padding: 16px 20px 16px 52px;
  border-radius: 16px; border: 1px solid var(--border);
  background: var(--card); backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  color: var(--text); box-shadow: var(--shadow); outline: none; font-weight: 500;
}
.search-bar input:focus { border-color: var(--accent); }
.search-bar::before {
  content: "🔍"; position: absolute; left: 20px; top: 50%;
  transform: translateY(-50%); font-size: 1.1rem; opacity: 0.6; pointer-events: none;
}
.tabs { display: flex; gap: 8px; overflow-x: auto; padding: 4px 2px 12px; margin-bottom: 8px; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab {
  flex-shrink: 0; padding: 9px 16px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--card); backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  color: var(--text-2); font-size: 0.92rem; font-weight: 600; cursor: pointer; white-space: nowrap;
}
.tab.active { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: white; border-color: transparent; }
.group { margin-bottom: 28px; }
.group-title {
  font-size: 1.3rem; font-weight: 800; margin: 24px 6px 14px;
  display: flex; align-items: center; gap: 12px;
}
.group-title::before {
  content: ""; width: 5px; height: 22px;
  background: linear-gradient(180deg, var(--accent), var(--accent-2)); border-radius: 4px;
}
.group-title .count {
  font-size: 0.78rem; font-weight: 700; color: var(--muted);
  background: var(--card); border: 1px solid var(--border);
  padding: 3px 11px; border-radius: 999px;
}
.card {
  display: flex; align-items: center; gap: 14px;
  background: var(--card); backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  border: 1px solid var(--border); border-radius: 18px;
  padding: 20px; margin-bottom: 12px;
  text-decoration: none; color: var(--text);
  box-shadow: var(--shadow); transition: transform 0.15s, border-color 0.15s;
}
.card:active { transform: scale(0.985); border-color: var(--accent); }
.title { font-size: 1.15rem; font-weight: 600; line-height: 1.45; word-break: break-word; }
.card-body { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.summary { font-size: 0.92rem; color: var(--muted); line-height: 1.45; word-break: break-word; }
.arrow { font-size: 1.7rem; color: var(--muted); flex-shrink: 0; }
.empty { text-align: center; color: var(--muted); padding: 80px 0; }
footer {
  text-align: center; margin-top: 50px; padding: 24px 0;
  border-top: 1px solid var(--border); font-size: 0.88rem; color: var(--muted); line-height: 1.8;
}
.to-top {
  position: fixed; right: 18px; bottom: calc(env(safe-area-inset-bottom) + 22px);
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: white; border: none; font-size: 1.5rem; font-weight: 700;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4); cursor: pointer;
  opacity: 0; transform: translateY(20px); transition: all 0.25s; z-index: 100;
}
.to-top.show { opacity: 1; transform: translateY(0); }
.hidden { display: none !important; }
</style>
</head>
<body>
<div class="wrapper">
  <header>
    <h1>🤖 AI 工具情报站</h1>
    <p class="subtitle">每天 5 分钟，跟上全球 AI 圈</p>
    <div class="stats">
      <span>📰 <b>__TOTAL__</b> 条</span>
      <span class="dot"></span>
      <span>📡 <b>__SOURCES__</b> 个源</span>
      <span class="dot"></span>
      <span>🕒 __TIME__</span>
    </div>
  </header>
  <div class="search-bar">
    <input id="search" type="search" placeholder="搜索 AI 工具、论文、新闻…" autocomplete="off">
  </div>
  <div class="tabs" id="tabs"></div>
  <main id="content">
__BODY__
  </main>
  <footer>
    <p>🤖 Powered by GitHub Actions · 每天 8:00 自动更新</p>
  </footer>
</div>
<button class="to-top" id="toTop" aria-label="回到顶部">↑</button>
<script>
const groups = document.querySelectorAll('.group');
const sources = ['全部', ...Array.from(groups).map(g => g.dataset.source)];
const tabsEl = document.getElementById('tabs');
sources.forEach((s, i) => {
  const b = document.createElement('button');
  b.className = 'tab' + (i === 0 ? ' active' : '');
  b.textContent = s;
  b.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    b.classList.add('active');
    groups.forEach(g => g.classList.toggle('hidden', i !== 0 && g.dataset.source !== s));
  };
  tabsEl.appendChild(b);
});
const search = document.getElementById('search');
search.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(card => {
    const t = card.querySelector('.title').textContent.toLowerCase();
    card.classList.toggle('hidden', q && !t.includes(q));
  });
  groups.forEach(g => {
    const visible = g.querySelectorAll('.card:not(.hidden)').length;
    g.classList.toggle('hidden', visible === 0);
  });
});
const toTop = document.getElementById('toTop');
window.addEventListener('scroll', () => {
  toTop.classList.toggle('show', window.scrollY > 400);
}, { passive: true });
toTop.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
</script>
</body>
</html>"""
def build_html(articles):
    bj = datetime.now(timezone(timedelta(hours=8)))
    stamp = bj.strftime("%m-%d %H:%M")
    by_source = {}
    for a in articles:
        by_source.setdefault(a["source"], []).append(a)
    sections = []
    for source, items in by_source.items():
        cards = "\n".join(
            f'      <a class="card" href="{html.escape(it["link"])}" target="_blank" rel="noopener">'
            f'<div class="card-body"><span class="title">{html.escape(it["title"])}</span>'
            + (f'<span class="summary">{html.escape(it.get("summary",""))}</span>' if it.get("summary") else "")
            + f'</div><span class="arrow">›</span></a>'
            for it in items
        )
        sections.append(
            f'    <section class="group" data-source="{html.escape(source)}">\n'
            f'      <h2 class="group-title">{html.escape(source)}'
            f' <span class="count">{len(items)}</span></h2>\n'
            f'{cards}\n'
            f'    </section>'
        )
    body = "\n".join(sections) if sections else '    <p class="empty">暂无内容</p>'
    return (HTML_TEMPLATE
            .replace("__TOTAL__", str(len(articles)))
            .replace("__SOURCES__", str(len(by_source)))
            .replace("__TIME__", stamp)
            .replace("__BODY__", body))
def main():
    all_items = []
    for name, url in FEEDS.items():
        all_items.extend(parse_feed(name, url))
    os.makedirs("public", exist_ok=True)
    out = os.path.join("public", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(all_items))
    print(f"\nDone: {out} ({len(all_items)} items)")
if __name__ == "__main__":
    main()
