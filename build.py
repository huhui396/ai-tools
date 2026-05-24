
"""
AI 工具情报站 - 每天自动聚合 AI 领域信息源
"""
import html
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import feedparser
import requests

SITE_URL = "https://huhui396.github.io/ai-tools/"
LATEST_LIMIT = 40
# 抓到的有效条目少于这个数,视为构建失败:不写文件、不部署,保住上一版线上页面
MIN_ITEMS = 5

# 两个页面共用的设计变量与基础重置,集中维护,避免改主题色要改两处
SHARED_CSS = r""":root {
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
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }"""
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
HEADERS = {
    "User-Agent": UA,
    "Accept": ("application/rss+xml, application/atom+xml, "
               "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
RETRIES = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
def fetch(url):
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code in RETRY_STATUS and attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.content
        except requests.HTTPError as e:
            # 4xx 或已耗尽重试的 5xx:硬失败,重试无意义
            print(f"  fail: {e}")
            return None
        except Exception as e:
            # 网络类错误(超时/连接):退避后重试
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"  fail: {e}")
            return None
def parse_feed(name, url):
    print(f"-> {name}")
    raw = fetch(url)
    if not raw:
        return []
    parsed = feedparser.parse(raw)
    items = []
    now = datetime.now(timezone.utc)
    for entry in parsed.entries[:PER_FEED_LIMIT]:
        summary = entry.get("summary") or entry.get("description") or ""
        summary = re.sub(r"<[^>]+>", "", summary).strip()[:80]
        # 解析发布时间
        pub_str = ""
        is_new = False
        ts = 0.0
        pub_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub_parsed:
            try:
                pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                ts = pub_dt.timestamp()
                delta = now - pub_dt
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    pub_str = "刚刚"
                    is_new = True
                elif hours < 24:
                    pub_str = f"{int(hours)} 小时前"
                    is_new = True
                elif hours < 24 * 7:
                    pub_str = f"{int(hours / 24)} 天前"
                else:
                    pub_str = pub_dt.strftime("%m-%d")
            except Exception:
                pass
        items.append({
            "title": (entry.get("title") or "无标题").strip(),
            "link": (entry.get("link") or "#").strip(),
            "source": name,
            "summary": summary,
            "pub_str": pub_str,
            "is_new": is_new,
            "ts": ts,
        })
    print(f"  ok: {len(items)}")
    return items
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#eef2ff" media="(prefers-color-scheme: light)">
<title>🤖 AI 工具情报站</title>
<meta name="description" content="自动聚合 ProductHunt、HackerNews、OpenAI、Anthropic 等 AI 信息源,中英文源,每天更新">
<meta property="og:title" content="AI 工具情报站 - 每天 5 分钟跟上全球 AI 圈">
<meta property="og:description" content="自动聚合 ProductHunt、HackerNews、OpenAI、Anthropic 等 AI 信息源,中英文源,每天更新">
<meta property="og:url" content="https://huhui396.github.io/ai-tools/">
<meta property="og:type" content="website">
<meta property="og:locale" content="zh_CN">
<meta property="og:image" content="https://huhui396.github.io/ai-tools/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="AI 工具情报站">
<meta name="twitter:description" content="每天 5 分钟,跟上全球 AI 圈">
<meta name="twitter:image" content="https://huhui396.github.io/ai-tools/og.png">
<link rel="canonical" href="https://huhui396.github.io/ai-tools/">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🤖%3C/text%3E%3C/svg%3E">
<style>
/*__SHARED_CSS__*/
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
header { text-align: center; padding: 20px 12px 16px; }
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
  display: inline-flex; align-items: center; gap: 14px; margin-top: 14px;
  font-size: 0.9rem; color: var(--text-2);
  background: var(--card); backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
  padding: 10px 20px; border-radius: 999px;
  border: 1px solid var(--border); box-shadow: var(--shadow);
}
.stats b { color: var(--accent); font-weight: 800; font-size: 1.05rem; }
.stats .dot { width: 4px; height: 4px; background: var(--muted); border-radius: 50%; }
.search-bar { position: sticky; top: 8px; z-index: 50; margin: 16px 0 16px; }
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
.tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 4px 2px 12px;
  margin-bottom: 8px;
  scrollbar-width: none;
  mask-image: linear-gradient(to right, black 88%, transparent);
  -webkit-mask-image: linear-gradient(to right, black 88%, transparent);
}
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
.summary { font-size: 0.92rem; color: var(--muted); line-height: 1.45; word-break: break-word; }
.arrow { font-size: 1.7rem; color: var(--accent); flex-shrink: 0; opacity: 0.6; transition: opacity 0.15s; }
.card:active .arrow { opacity: 1; }
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
.badges {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 10px;
  flex-wrap: wrap;
}
.badge {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-2);
  background: var(--card);
  border: 1px solid var(--border);
  padding: 4px 10px;
  border-radius: 999px;
  backdrop-filter: var(--blur);
  -webkit-backdrop-filter: var(--blur);
}
.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.card-title-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}
.new-badge {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 800;
  color: white;
  background: linear-gradient(135deg, #ef4444, #f97316);
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.05em;
  flex-shrink: 0;
  margin-top: 4px;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}
.card-meta {
  font-size: 0.78rem;
  color: var(--muted);
  font-weight: 500;
}
.next-update {
  text-align: center;
  margin-top: 8px;
  font-size: 0.82rem;
  color: var(--muted);
  font-weight: 500;
}
.header-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 16px;
}
.action-btn {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-2);
  background: var(--card);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: var(--blur);
  -webkit-backdrop-filter: var(--blur);
  transition: all 0.15s;
}
.action-btn:active {
  transform: scale(0.96);
  border-color: var(--accent);
}
.hidden { display: none !important; }
</style>
</head>
<body>
<div class="wrapper">
  <header>
    <h1>🤖 AI 工具情报站</h1>
    <p class="subtitle">每天 5 分钟，跟上全球 AI 圈</p>
    <div class="badges">
      <span class="badge">🆓 免费</span>
      <span class="badge">🚫 无广告</span>
      <span class="badge">🔄 24h 自动更新</span>
    </div>
    <div class="stats">
      <span>📰 <b>__TOTAL__</b> 条</span>
      <span class="dot"></span>
      <span>📡 <b>__SOURCES__</b> 个源</span>
      <span class="dot"></span>
      <span>🕒 __TIME__</span>
    </div>
    <div class="next-update">⏰ 下次更新 __NEXT_UPDATE__</div>
    <div class="header-actions">
      <button class="action-btn" onclick="shareNow()">🔗 分享给朋友</button>
    </div>
  </header>
  <div class="search-bar">
    <input id="search" type="search" placeholder="搜索 AI 工具、论文、新闻…" autocomplete="off">
  </div>
  <div class="tabs" id="tabs"></div>
  <main id="content">
__BODY__
  </main>
  <p class="empty hidden" id="noResults">🔍 没有找到相关内容，换个关键词试试</p>
  <footer>
    <p>🤖 Powered by GitHub Actions · 每天 8:00 自动更新</p>
    <p style="margin-top:6px">📡 12 个精选中英文 AI 信息源 · 开源免费</p>
    <p style="margin-top:6px;font-size:0.8rem;">💡 觉得有用?把这个网址告诉一个朋友</p>
    <p style="margin-top:14px"><a href="about.html" style="color:var(--accent);text-decoration:none;font-weight:600;">👋 关于本站</a></p>
  </footer>
</div>
<button class="to-top" id="toTop" aria-label="回到顶部">↑</button>
<script>
const allGroups = Array.from(document.querySelectorAll('.group'));
const latestGroup = document.querySelector('.latest-group');
const sourceGroups = allGroups.filter(g => !g.classList.contains('latest-group'));
const search = document.getElementById('search');
const noResults = document.getElementById('noResults');
const tabsEl = document.getElementById('tabs');
const tabNames = ['全部', ...(latestGroup ? ['🆕 最新'] : []), ...sourceGroups.map(g => g.dataset.source)];
let activeTab = '全部';

function cardMatches(card, q) {
  if (!q) return true;
  const t = card.querySelector('.title').textContent.toLowerCase();
  const s = card.querySelector('.summary');
  return t.includes(q) || (s ? s.textContent.toLowerCase().includes(q) : false);
}

function applyFilters() {
  const q = search.value.trim().toLowerCase();
  let anyVisible = false;
  allGroups.forEach(g => {
    const isLatest = g.classList.contains('latest-group');
    let inTab;
    if (activeTab === '全部') inTab = !isLatest;
    else if (activeTab === '🆕 最新') inTab = isLatest;
    else inTab = !isLatest && g.dataset.source === activeTab;
    if (!inTab) { g.classList.add('hidden'); return; }
    let visible = 0;
    g.querySelectorAll('.card').forEach(card => {
      const show = cardMatches(card, q);
      card.classList.toggle('hidden', !show);
      if (show) visible++;
    });
    g.classList.toggle('hidden', visible === 0);
    if (visible > 0) anyVisible = true;
  });
  noResults.classList.toggle('hidden', anyVisible);
}

tabNames.forEach((s, i) => {
  const b = document.createElement('button');
  b.className = 'tab' + (i === 0 ? ' active' : '');
  b.textContent = s;
  b.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    b.classList.add('active');
    activeTab = s;
    applyFilters();
  };
  tabsEl.appendChild(b);
});
search.addEventListener('input', applyFilters);
applyFilters();
const toTop = document.getElementById('toTop');
window.addEventListener('scroll', () => {
  toTop.classList.toggle('show', window.scrollY > 400);
}, { passive: true });
toTop.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
function shareNow() {
  const url = 'https://huhui396.github.io/ai-tools/';
  const text = 'AI 工具情报站 - 每天 5 分钟,跟上全球 AI 圈';
  if (navigator.share) {
    navigator.share({ title: text, url: url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(url).then(() => {
      alert('链接已复制!');
    });
  }
}
</script>
<!-- GoatCounter 访问统计 -->
<script data-goatcounter="https://airadar.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
</body>
</html>"""
ABOUT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#eef2ff" media="(prefers-color-scheme: light)">
<title>关于 - AI 工具情报站</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🤖%3C/text%3E%3C/svg%3E">
<style>
/*__SHARED_CSS__*/
html { font-size: 18px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  background-image: var(--bg-grad);
  background-attachment: fixed;
  color: var(--text);
  line-height: 1.7;
  padding: max(env(safe-area-inset-top), 16px) 20px calc(env(safe-area-inset-bottom) + 60px);
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}
.wrapper { max-width: 680px; margin: 0 auto; }
header { text-align: center; padding: 20px 0 28px; }
header h1 {
  font-size: 1.8rem;
  font-weight: 900;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.intro {
  background: var(--card);
  backdrop-filter: var(--blur);
  -webkit-backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 22px 24px;
  margin-bottom: 22px;
  box-shadow: var(--shadow);
  font-size: 1rem;
  color: var(--text-2);
}
.intro strong { color: var(--text); }
.section {
  background: var(--card);
  backdrop-filter: var(--blur);
  -webkit-backdrop-filter: var(--blur);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 22px 24px;
  margin-bottom: 18px;
  box-shadow: var(--shadow);
}
.section h2 {
  font-size: 1.05rem;
  font-weight: 800;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.section h2::before {
  content: "";
  width: 4px;
  height: 18px;
  background: linear-gradient(180deg, var(--accent), var(--accent-2));
  border-radius: 4px;
}
.section ul { list-style: none; padding: 0; }
.section li {
  font-size: 0.95rem;
  color: var(--text-2);
  padding: 5px 0;
  line-height: 1.6;
}
.section p {
  font-size: 0.95rem;
  color: var(--text-2);
  margin-bottom: 8px;
}
.section a { color: var(--accent); text-decoration: none; font-weight: 600; }
.promise li {
  font-weight: 600;
  color: var(--text);
}
.back {
  display: inline-block;
  margin-top: 24px;
  font-size: 1rem;
  color: var(--accent);
  text-decoration: none;
  font-weight: 700;
  padding: 12px 24px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 999px;
  backdrop-filter: var(--blur);
  -webkit-backdrop-filter: var(--blur);
}
.center { text-align: center; }
.footer-quote {
  text-align: center;
  margin-top: 28px;
  padding: 20px;
  font-style: italic;
  color: var(--muted);
  font-size: 0.92rem;
}
</style>
</head>
<body>
<div class="wrapper">
  <header>
    <h1>👋 关于 AI 工具情报站</h1>
  </header>

  <div class="intro">
    Hi,我是 <strong>AIRadar 🛰</strong><br><br>
    我是一个对 AI 行业感兴趣的独立开发者,
    每天看不完 AI 新闻,所以做了这个工具,
    把 12 个最好的 AI 信息源聚合到一起,
    每天自动抓取、去重、按时间排好,一页看完。
  </div>

  <section class="section">
    <h2>📡 信息源</h2>
    <ul>
      <li>• Anthropic / OpenAI / Hugging Face 官方博客</li>
      <li>• Product Hunt AI 新品发布</li>
      <li>• The Decoder / VentureBeat / MIT Tech Review</li>
      <li>• ArXiv AI 最新论文</li>
      <li>• Hacker News (AI 相关)</li>
      <li>• 机器之心 / 量子位 (中文)</li>
    </ul>
  </section>

  <section class="section">
    <h2>✅ 我的承诺</h2>
    <ul class="promise">
      <li>✓ 完全免费</li>
      <li>✓ 无广告</li>
      <li>✓ 不追踪用户</li>
      <li>✓ 不收集邮箱</li>
      <li>✓ 开源(代码在 GitHub)</li>
    </ul>
  </section>

  <section class="section">
    <h2>🛠 怎么实现的</h2>
    <p>GitHub Actions 每天 8:00 自动跑<br>
    + Python 并行抓取 12 个 RSS 源(自动去重)<br>
    + GitHub Pages 静态托管</p>
  </section>

  <section class="section">
    <h2>📮 联系我</h2>
    <p><strong>GitHub:</strong> <a href="https://github.com/huhui396/ai-tools" target="_blank">github.com/huhui396/ai-tools</a></p>
    <p><strong>Reddit:</strong> <a href="https://reddit.com/user/AIRadarDaily" target="_blank">u/AIRadarDaily</a></p>
  </section>

  <p class="footer-quote">如果你觉得有用,请把这个网站告诉一个朋友 💛</p>

  <div class="center">
    <a class="back" href="./">← 返回首页</a>
  </div>
</div>
</body>
</html>"""
def build_html(articles):
    bj = datetime.now(timezone(timedelta(hours=8)))
    stamp = bj.strftime("%m-%d %H:%M")
    # 下次更新时间 (北京时间次日 8:00)
    next_update = (bj + timedelta(days=1)).replace(hour=8, minute=0, second=0)
    # 如果当前还没到今天 8:00,下次就是今天 8:00
    today_8am = bj.replace(hour=8, minute=0, second=0)
    if bj < today_8am:
        next_update = today_8am
    next_update_str = next_update.strftime("%m-%d %H:%M")
    by_source = {}
    for a in articles:
        by_source.setdefault(a["source"], []).append(a)

    def render_card(it):
        title = html.escape(it["title"])
        arrow = '<span class="arrow">›</span>'
        new_badge = '<span class="new-badge">NEW</span>' if it.get("is_new") else ''
        pub_str = html.escape(it.get("pub_str", ""))
        summary = html.escape(it.get("summary", ""))
        summary_html = f'<span class="summary">{summary}</span>' if it.get("summary") else ''
        meta = f'<div class="card-meta">{pub_str}</div>' if pub_str else ''
        return (
            f'      <a class="card" href="{html.escape(it["link"])}" target="_blank" rel="noopener">'
            f'<div class="card-content">'
            f'<div class="card-title-row"><span class="title">{title}</span>{new_badge}</div>'
            f'{summary_html}'
            f'{meta}'
            f'</div>'
            f'{arrow}</a>'
        )

    sections = []
    # 🆕 最新:跨所有源按发布时间倒序,默认隐藏,由"最新"标签切出
    recent = sorted((a for a in articles if a.get("ts")),
                    key=lambda a: a["ts"], reverse=True)[:LATEST_LIMIT]
    if recent:
        cards = "\n".join(render_card(it) for it in recent)
        sections.append(
            f'    <section class="group latest-group hidden" data-source="🆕 最新">\n'
            f'      <h2 class="group-title">🆕 最新'
            f' <span class="count">{len(recent)}</span></h2>\n'
            f'{cards}\n'
            f'    </section>'
        )
    for source, items in by_source.items():
        cards = "\n".join(render_card(it) for it in items)
        sections.append(
            f'    <section class="group" data-source="{html.escape(source)}">\n'
            f'      <h2 class="group-title">{html.escape(source)}'
            f' <span class="count">{len(items)}</span></h2>\n'
            f'{cards}\n'
            f'    </section>'
        )
    body = "\n".join(sections) if sections else '    <p class="empty">暂无内容</p>'
    return (HTML_TEMPLATE
            .replace("/*__SHARED_CSS__*/", SHARED_CSS)
            .replace("__TOTAL__", str(len(articles)))
            .replace("__SOURCES__", str(len(by_source)))
            .replace("__TIME__", stamp)
            .replace("__NEXT_UPDATE__", next_update_str)
            .replace("__BODY__", body))
def dedup(items):
    """按链接去重(跨源),保留首次出现的顺序。"""
    seen = set()
    out = []
    for it in items:
        link = (it.get("link") or "").split("?")[0].rstrip("/").lower()
        if link and link != "#":
            if link in seen:
                continue
            seen.add(link)
        out.append(it)
    return out


def write_site_files():
    """生成 sitemap.xml 与 robots.txt,利于搜索引擎收录。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{SITE_URL}</loc><lastmod>{today}</lastmod>'
        '<changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        f'  <url><loc>{SITE_URL}about.html</loc>'
        '<changefreq>monthly</changefreq><priority>0.5</priority></url>\n'
        '</urlset>\n'
    )
    robots = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n"
    with open(os.path.join("public", "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    with open(os.path.join("public", "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots)


def generate_og_image(path):
    """生成 1200x630 社交分享图(拉丁品牌文案)。失败不影响站点构建。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print(f"  og skip (Pillow unavailable): {e}")
        return
    try:
        W, H = 1200, 630
        top, bot = (37, 99, 235), (124, 58, 237)
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):
            r = top[0] + (bot[0] - top[0]) * y // H
            g = top[1] + (bot[1] - top[1]) * y // H
            b = top[2] + (bot[2] - top[2]) * y // H
            for x in range(W):
                px[x, y] = (r, g, b)
        draw = ImageDraw.Draw(img)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        def load(size):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                return ImageFont.load_default()

        def centered(text, font, y, fill):
            box = draw.textbbox((0, 0), text, font=font)
            draw.text(((W - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

        centered("AI RADAR", load(150), 150, (255, 255, 255))
        centered("Daily AI intelligence, in one place",
                 load(46), 340, (235, 238, 252))
        centered("ProductHunt  HackerNews  OpenAI  Anthropic  arXiv",
                 load(30), 430, (210, 215, 245))
        centered("huhui396.github.io/ai-tools", load(28), 540, (200, 205, 240))
        img.save(path, "PNG")
        print(f"Done: {path}")
    except Exception as e:
        print(f"  og fail: {e}")


def main():
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda kv: parse_feed(*kv), FEEDS.items()))
    all_items = dedup([it for items in results for it in items])

    if len(all_items) < MIN_ITEMS:
        print(f"\nABORT: only {len(all_items)} items (< {MIN_ITEMS}). "
              f"Skip writing/deploy to keep the last good site.")
        sys.exit(1)

    os.makedirs("public", exist_ok=True)
    out = os.path.join("public", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(all_items))
    # 生成 about 页面
    about_out = os.path.join("public", "about.html")
    with open(about_out, "w", encoding="utf-8") as f:
        f.write(ABOUT_HTML.replace("/*__SHARED_CSS__*/", SHARED_CSS))
    write_site_files()
    generate_og_image(os.path.join("public", "og.png"))
    print(f"Done: {about_out}")
    print(f"\nDone: {out} ({len(all_items)} items)")
if __name__ == "__main__":
    main()
