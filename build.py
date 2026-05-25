
"""
AI 工具情报站 - 每天自动聚合 AI 领域信息源
"""
import html
import json
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
  --bg: #fafafa;
  --bg-grad: radial-gradient(900px 480px at 50% -340px,
             color-mix(in srgb, var(--accent) 9%, transparent), transparent 62%),
             var(--bg);
  --card: #ffffff;
  --card-hover: #fbfbfc;
  --text: #0a0a0a;
  --text-2: #3f3f46;
  --muted: #71717a;
  --accent: #4f46e5;
  --accent-soft: color-mix(in srgb, var(--accent) 12%, transparent);
  --border: rgba(9, 9, 11, 0.07);
  --border-strong: rgba(9, 9, 11, 0.13);
  --shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px -14px rgba(15, 23, 42, 0.16);
  --shadow-lg: 0 1px 2px rgba(15, 23, 42, 0.05), 0 18px 38px -16px rgba(15, 23, 42, 0.26);
  --r: 12px;
  --r-pill: 999px;
  --blur: blur(14px) saturate(160%);
  --ease: cubic-bezier(.16, 1, .3, 1);
  --card-border: rgba(9, 9, 11, 0);
  --card-shadow: 0 6px 24px rgba(15, 23, 42, 0.05);
  --card-shadow-hover: 0 14px 36px -6px rgba(15, 23, 42, 0.10);
  --tab-active: #4338ca;
  --new-fg: #7c3aed;
  --ic-search: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='M21 21l-3.6-3.6'/%3E%3C/svg%3E");
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0a0a0b;
    --card: #141519;
    --card-hover: #181a20;
    --text: #fafafa;
    --text-2: #d4d4d8;
    --muted: #8b8b94;
    --accent: #818cf8;
    --border: rgba(255, 255, 255, 0.08);
    --border-strong: rgba(255, 255, 255, 0.15);
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 8px 24px -14px rgba(0, 0, 0, 0.6);
    --shadow-lg: 0 1px 2px rgba(0, 0, 0, 0.5), 0 18px 38px -16px rgba(0, 0, 0, 0.7);
    --card-border: rgba(255, 255, 255, 0.07);
    --card-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
    --card-shadow-hover: 0 14px 36px rgba(0, 0, 0, 0.55);
    --tab-active: #6366f1;
    --new-fg: #a78bfa;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }"""
FEEDS = {
    "Product Hunt":    "https://www.producthunt.com/feed?category=artificial-intelligence",
    "The Decoder":     "https://the-decoder.com/feed/",
    "VentureBeat AI":  "https://venturebeat.com/category/ai/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "ArXiv AI":        "http://export.arxiv.org/rss/cs.AI",
    "Hacker News":     "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT&count=15",
    "GitHub Trending": "https://rsshub.app/github/trending/daily/Python",
    "OpenAI Blog":     "https://openai.com/blog/rss.xml",
    "Anthropic":       "https://www.anthropic.com/news/rss.xml",
    "Hugging Face":    "https://huggingface.co/blog/feed.xml",
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
        summary = html.unescape(re.sub(r"<[^>]+>", "", summary))
        # 砍掉 Hacker News 等源的 "Article URL: … Comments URL: …" 样板
        summary = re.split(r"(?:Article|Comments)\s+URL\s*:", summary, maxsplit=1)[0]
        # 去掉任何裸露的长链接,避免原始数据暴露在卡片里
        summary = re.sub(r"https?://\S+", "", summary)
        summary = re.sub(r"\s*\b(Discussion|Comments?)\b\s*[|·–—-].*$", "", summary, flags=re.I)
        summary = re.sub(r"\s+", " ", summary).strip()[:120]
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
<meta name="theme-color" content="#0a0a0b" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<title>🛰️ AI 工具情报站</title>
<meta name="description" content="自动聚合 ProductHunt、HackerNews、OpenAI、Anthropic 等全球 AI 信息源,每天更新">
<meta property="og:title" content="AI 工具情报站 - 每天 5 分钟跟上全球 AI 圈">
<meta property="og:description" content="自动聚合 ProductHunt、HackerNews、OpenAI、Anthropic 等全球 AI 信息源,每天更新">
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
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="AI 情报站">
<meta name="mobile-web-app-capable" content="yes">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🛰️%3C/text%3E%3C/svg%3E">
<style>
/*__SHARED_CSS__*/
html { font-size: 16px; scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  background-image: var(--bg-grad);
  background-attachment: fixed;
  color: var(--text);
  line-height: 1.5;
  padding: max(env(safe-area-inset-top), 16px) 18px calc(env(safe-area-inset-bottom) + 80px);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  min-height: 100vh;
}
.wrapper { max-width: 720px; margin: 0 auto; }
header { text-align: center; padding: 30px 12px 10px; }
header h1 {
  display: flex; align-items: center; justify-content: center; gap: 11px;
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}
header h1 .logo { width: 30px; height: 30px; flex-shrink: 0; }
header .subtitle { font-size: 0.9375rem; color: var(--muted); margin-top: 13px; font-weight: 400; letter-spacing: 0.04em; }
.stats {
  display: inline-flex; align-items: center; gap: 11px; margin-top: 20px;
  font-size: 0.8125rem; color: var(--muted);
  background: color-mix(in srgb, var(--card) 60%, transparent);
  backdrop-filter: blur(12px) saturate(140%); -webkit-backdrop-filter: blur(12px) saturate(140%);
  padding: 8px 18px; border-radius: var(--r-pill);
  border: 1px solid var(--border); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.stats b { color: var(--text); font-weight: 700; font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
.stats .sep { color: var(--border-strong); font-weight: 300; }
.header-actions { display: flex; justify-content: center; gap: 10px; margin-top: 18px; }
.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 0.8125rem; font-weight: 500; color: var(--text-2);
  background: transparent; border: 1px solid var(--border-strong);
  padding: 7px 15px; border-radius: var(--r-pill); cursor: pointer;
  transition: background .18s var(--ease), color .18s var(--ease), border-color .18s var(--ease);
}
.action-btn svg { width: 15px; height: 15px; }
@media (hover: hover) {
  .action-btn:hover { background: var(--card-hover); color: var(--text); border-color: var(--muted); }
}
.action-btn:active { transform: translateY(1px); }
.filter-bar {
  position: sticky; top: 0; z-index: 50;
  margin: 18px -18px 8px; padding: 12px 18px 0;
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
}
.search-bar { position: relative; }
.search-bar input {
  width: 100%; font-size: 0.9063rem; padding: 10px 18px 10px 44px;
  border-radius: var(--r); border: 1px solid var(--border);
  background: var(--card);
  color: var(--text); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03); outline: none; font-weight: 450;
  transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
}
.search-bar input::placeholder { color: var(--muted); }
.search-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.search-bar::before {
  content: ""; position: absolute; left: 16px; top: 50%;
  transform: translateY(-50%); width: 17px; height: 17px; pointer-events: none;
  background: var(--muted);
  -webkit-mask: var(--ic-search) center / contain no-repeat;
  mask: var(--ic-search) center / contain no-repeat;
}
.tabs {
  display: flex;
  gap: 7px;
  overflow-x: auto;
  padding: 0 2px 12px;
  scrollbar-width: none;
  mask-image: linear-gradient(to right, black 90%, transparent);
  -webkit-mask-image: linear-gradient(to right, black 90%, transparent);
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
  flex-shrink: 0; padding: 8px 15px; border-radius: var(--r-pill); border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2); font-size: 0.8125rem; font-weight: 500; cursor: pointer; white-space: nowrap;
  transition: background .18s var(--ease), color .18s var(--ease), border-color .18s var(--ease),
              transform .18s var(--ease), box-shadow .18s var(--ease);
}
.tab.active {
  background: var(--tab-active); color: #fff; border-color: transparent;
  box-shadow: 0 4px 12px -4px color-mix(in srgb, var(--tab-active) 50%, transparent);
}
@media (hover: hover) {
  .tab:hover:not(.active) {
    color: var(--text); border-color: var(--border-strong);
    background: var(--card-hover); transform: translateY(-1px);
  }
}
.group { margin-bottom: 8px; }
.group-title {
  font-size: 1.0625rem; font-weight: 600; letter-spacing: -0.01em;
  margin: 34px 4px 14px;
  display: flex; align-items: center; gap: 10px; color: var(--text);
}
.group-title::before {
  content: ""; width: 3px; height: 16px;
  background: var(--accent); border-radius: 2px;
}
.group-title .count {
  font-size: 0.6875rem; font-weight: 600; color: var(--muted);
  background: var(--card); border: 1px solid var(--border);
  padding: 2px 9px; border-radius: var(--r-pill);
}
.card {
  display: flex; align-items: center; gap: 14px;
  background: var(--card);
  border: 1px solid var(--card-border); border-radius: 16px;
  padding: 18px 20px; margin-bottom: 12px;
  text-decoration: none; color: var(--text);
  box-shadow: var(--card-shadow);
  transition: transform .25s var(--ease), box-shadow .25s var(--ease);
}
@media (hover: hover) {
  .card:hover { transform: translateY(-2px); box-shadow: var(--card-shadow-hover); }
  .card:hover .arrow { opacity: 1; transform: translateX(3px); }
}
.card:active { transform: translateY(0); }
.title { font-size: 1.0625rem; font-weight: 600; line-height: 1.32; letter-spacing: -0.006em; word-break: break-word; color: var(--text); }
.summary {
  font-size: 0.875rem; color: var(--muted); line-height: 1.5; word-break: break-word;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.arrow {
  color: var(--muted); flex-shrink: 0; opacity: 0.5;
  display: flex; align-items: center;
  transition: opacity .22s var(--ease), transform .22s var(--ease);
}
.empty { text-align: center; color: var(--muted); padding: 80px 0; font-size: 0.9375rem; }
footer {
  text-align: center; margin-top: 64px; padding: 28px 0 8px;
  border-top: 1px solid var(--border); font-size: 0.8125rem; color: var(--muted); line-height: 1.9;
}
.to-top {
  position: fixed; right: 18px; bottom: calc(env(safe-area-inset-bottom) + 22px);
  width: 46px; height: 46px; border-radius: 50%;
  background: var(--accent);
  color: #fff; border: none; font-size: 1.25rem; font-weight: 600;
  box-shadow: 0 6px 20px -6px color-mix(in srgb, var(--accent) 55%, transparent);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  opacity: 0; transform: translateY(16px) scale(0.9);
  transition: opacity .25s var(--ease), transform .25s var(--ease), background .2s var(--ease); z-index: 100;
}
.to-top.show { opacity: 1; transform: translateY(0) scale(1); }
@media (hover: hover) {
  .to-top:hover { background: color-mix(in srgb, var(--accent) 88%, #000); }
}
.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
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
  font-size: 0.625rem;
  font-weight: 700;
  color: var(--new-fg);
  background: color-mix(in srgb, var(--new-fg) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--new-fg) 20%, transparent);
  padding: 1px 7px;
  border-radius: var(--r-pill);
  letter-spacing: 0.04em;
  flex-shrink: 0;
  margin-top: 3px;
}
.card-meta {
  font-size: 0.75rem;
  color: var(--muted);
  font-weight: 450;
}
@media (prefers-reduced-motion: no-preference) {
  #content { animation: rise .45s var(--ease) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
}
.hidden { display: none !important; }
</style>
</head>
<body>
<div class="wrapper">
  <header>
    <h1><svg class="logo" viewBox="0 0 24 24" fill="none" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><defs><linearGradient id="logoGrad" x1="2" y1="3" x2="22" y2="21" gradientUnits="userSpaceOnUse"><stop stop-color="#2563eb"/><stop offset="1" stop-color="#7c3aed"/></linearGradient></defs><g stroke="url(#logoGrad)"><path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/></g></svg>AI 工具情报站</h1>
    <p class="subtitle">每天 5 分钟，跟上全球 AI 圈</p>
    <div class="stats">
      <span><b>__TOTAL__</b> 条</span>
      <span class="sep">|</span>
      <span><b>__SOURCES__</b> 个源</span>
      <span class="sep">|</span>
      <span>__TIME__ 更新</span>
    </div>
    <div class="header-actions">
      <button class="action-btn" onclick="shareNow()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>
        分享
      </button>
    </div>
  </header>
  <div class="filter-bar">
    <div class="search-bar">
      <input id="search" type="search" placeholder="搜索 AI 工具、论文、新闻…" autocomplete="off">
    </div>
    <div class="tabs" id="tabs"></div>
  </div>
  <main id="content">
__BODY__
  </main>
  <p class="empty hidden" id="noResults">没有找到相关内容，换个关键词试试</p>
  <footer>
    <p>每天 08:00 自动更新 · Powered by GitHub Actions</p>
    <p style="margin-top:6px">10 个精选全球 AI 信息源 · 开源免费</p>
    <p style="margin-top:14px"><a href="about.html" style="color:var(--accent);text-decoration:none;font-weight:500;">关于本站 →</a></p>
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
const tabNames = ['全部', ...(latestGroup ? ['最新'] : []), ...sourceGroups.map(g => g.dataset.source)];
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
    else if (activeTab === '最新') inTab = isLatest;
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
<script>
if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
</script>
</body>
</html>"""
ABOUT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a0a0b" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<title>关于 - AI 工具情报站</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🛰️%3C/text%3E%3C/svg%3E">
<style>
/*__SHARED_CSS__*/
html { font-size: 16px; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  background-image: var(--bg-grad);
  background-attachment: fixed;
  color: var(--text);
  line-height: 1.7;
  padding: max(env(safe-area-inset-top), 16px) 20px calc(env(safe-area-inset-bottom) + 60px);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  min-height: 100vh;
}
.wrapper { max-width: 640px; margin: 0 auto; }
header { text-align: center; padding: 32px 0 28px; }
header h1 {
  font-size: 1.6rem;
  font-weight: 700;
  letter-spacing: -0.022em;
  color: var(--text);
}
.intro {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 22px 24px;
  margin-bottom: 16px;
  box-shadow: var(--shadow);
  font-size: 0.9375rem;
  color: var(--text-2);
}
.intro strong { color: var(--text); font-weight: 600; }
.section {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 22px 24px;
  margin-bottom: 14px;
  box-shadow: var(--shadow);
}
.section h2 {
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.section h2::before {
  content: "";
  width: 3px;
  height: 15px;
  background: var(--accent);
  border-radius: 2px;
}
.section ul { list-style: none; padding: 0; }
.section li {
  font-size: 0.9063rem;
  color: var(--text-2);
  padding: 5px 0;
  line-height: 1.6;
}
.section p {
  font-size: 0.9063rem;
  color: var(--text-2);
  margin-bottom: 8px;
}
.section a { color: var(--accent); text-decoration: none; font-weight: 500; }
.promise li {
  font-weight: 500;
  color: var(--text);
}
.back {
  display: inline-block;
  margin-top: 28px;
  font-size: 0.9375rem;
  color: #fff;
  text-decoration: none;
  font-weight: 500;
  padding: 11px 24px;
  background: var(--accent);
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  box-shadow: 0 1px 2px rgba(0,0,0,.06), 0 6px 16px -7px color-mix(in srgb, var(--accent) 55%, transparent);
  transition: transform .18s var(--ease), background .18s var(--ease);
}
@media (hover: hover) {
  .back:hover { background: color-mix(in srgb, var(--accent) 90%, #000); }
}
.back:active { transform: translateY(1px); }
.center { text-align: center; }
.footer-quote {
  text-align: center;
  margin-top: 32px;
  padding: 20px;
  color: var(--muted);
  font-size: 0.875rem;
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
    把 10 个最好的 AI 信息源聚合到一起,
    每天自动抓取、去重、按时间排好,一页看完。
  </div>

  <section class="section">
    <h2>信息源</h2>
    <ul>
      <li>• Anthropic / OpenAI / Hugging Face 官方博客</li>
      <li>• Product Hunt AI 新品发布</li>
      <li>• The Decoder / VentureBeat / MIT Tech Review</li>
      <li>• ArXiv AI 最新论文</li>
      <li>• Hacker News (AI 相关)</li>
    </ul>
  </section>

  <section class="section">
    <h2>我的承诺</h2>
    <ul class="promise">
      <li>✓ 完全免费</li>
      <li>✓ 无广告</li>
      <li>✓ 不追踪用户</li>
      <li>✓ 不收集邮箱</li>
      <li>✓ 开源(代码在 GitHub)</li>
    </ul>
  </section>

  <section class="section">
    <h2>怎么实现的</h2>
    <p>GitHub Actions 每天 8:00 自动跑<br>
    + Python 并行抓取 10 个 RSS 源(自动去重)<br>
    + GitHub Pages 静态托管</p>
  </section>

  <section class="section">
    <h2>联系我</h2>
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
        arrow = ('<span class="arrow" aria-hidden="true">'
                 '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
                 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                 'stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></span>')
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
    # 最新:跨所有源按发布时间倒序,默认隐藏,由"最新"标签切出
    recent = sorted((a for a in articles if a.get("ts")),
                    key=lambda a: a["ts"], reverse=True)[:LATEST_LIMIT]
    if recent:
        cards = "\n".join(render_card(it) for it in recent)
        sections.append(
            f'    <section class="group latest-group hidden" data-source="最新">\n'
            f'      <h2 class="group-title">最新'
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
        link = (it.get("link") or "").split("#")[0].rstrip("/").lower()
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


def generate_icons():
    """生成 PWA 应用图标(纯色品牌底 + 白色 AI 字标)。失败不影响构建。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print(f"  icons skip (Pillow unavailable): {e}")
        return
    try:
        bg, fg = (79, 70, 229), (255, 255, 255)  # #4f46e5
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        for size, name in [(192, "icon-192.png"), (512, "icon-512.png"),
                           (180, "apple-touch-icon.png")]:
            img = Image.new("RGB", (size, size), bg)
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(font_path, int(size * 0.4))
            except Exception:
                font = ImageFont.load_default()
            box = d.textbbox((0, 0), "AI", font=font)
            d.text(((size - (box[2] - box[0])) / 2 - box[0],
                    (size - (box[3] - box[1])) / 2 - box[1]),
                   "AI", font=font, fill=fg)
            img.save(os.path.join("public", name), "PNG")
        print("Done: app icons")
    except Exception as e:
        print(f"  icons fail: {e}")


def write_pwa():
    """生成 manifest.json 与 service worker,使站点可安装、可离线。"""
    manifest = {
        "name": "AI 工具情报站",
        "short_name": "AI 情报站",
        "description": "每天自动聚合全球 AI 信息源,5 分钟跟上 AI 圈",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#fafafa",
        "theme_color": "#fafafa",
        "lang": "zh-CN",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png",
             "purpose": "any maskable"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "any maskable"},
        ],
    }
    with open(os.path.join("public", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # network-first:在线总是拿最新,离线回退到缓存
    sw = """const CACHE = 'airadar-v1';
const CORE = ['./', './index.html', './about.html', './og.png', './manifest.json',
              './icon-192.png', './icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req).then(m => m || caches.match('./index.html')))
  );
});
"""
    with open(os.path.join("public", "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw)


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
    generate_icons()
    write_pwa()
    print(f"Done: {about_out}")
    print(f"\nDone: {out} ({len(all_items)} items)")
if __name__ == "__main__":
    main()
