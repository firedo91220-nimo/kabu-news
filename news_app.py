# news_app.py
# --------------------------------------------------------------------
# 日本株ニュース・ダッシュボード
#
# ・日本株の値動きに関係する「世界のニュース」と「日本のニュース」を
#   1画面でいっきに確認するためのアプリ。
# ・APIキー不要・無料。
#     - ニュースは RSS（NHK / Yahoo!ニュース）から取得
#     - 上部の相場サマリーは yfinance（= Yahoo Finance）から取得
# ・このファイルを実行すると、同じフォルダに「news.html」を作って
#   ブラウザで自動的に開きます。最新にしたいときは、もう一度実行するだけ。
#
# ＜カテゴリ＞
#   1) アメリカ・世界市場   2) 為替（ドル円）
#   3) 日本経済・日銀       4) 企業・個別株
#   （どれにも当てはまらない主要ニュースは「その他」に表示）
# --------------------------------------------------------------------

import os
import sys
import html
import time
import webbrowser
from datetime import datetime, timezone, timedelta

import requests
import feedparser

# 文字化け対策（コンソール出力をUTF-8に）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 日本時間（JST = UTC+9）
JST = timezone(timedelta(hours=9))

# 自動更新の間隔（分）。開いている間、この間隔でニュース・相場を取り直します。
REFRESH_MIN = 10
# クラウド（GitHub Actions）で自動更新するときの間隔（分）。PCオフでも更新される。
CLOUD_REFRESH_MIN = 30


# ====================================================================
# ① ニュースの取得元（RSS）。ここを足せばニュース源を増やせます。
#    形式：(表示名, RSSのURL)
# ====================================================================
def google_news_rss(query):
    """Googleニュースの「検索RSS」のURLを作る（日本語・日本向け）。
    ・例: google_news_rss("site:jp.reuters.com when:3d")
        site:ドメイン … その媒体だけに絞る ／ when:3d … 直近3日に絞る
    ブルームバーグ・ロイターは公式の無料RSSをほぼ閉じているため、
    Googleニュース経由で日本語記事を取得しています。"""
    return requests.Request(
        "GET", "https://news.google.com/rss/search",
        params={"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"},
    ).prepare().url


FEEDS = [
    # 日本株に関係しやすい「経済」「国際」を中心にしています。
    ("NHK", "https://www3.nhk.or.jp/rss/news/cat5.xml"),            # NHK 経済
    ("NHK", "https://www3.nhk.or.jp/rss/news/cat6.xml"),            # NHK 国際
    ("Yahoo", "https://news.yahoo.co.jp/rss/topics/business.xml"),  # Yahoo!ニュース 経済
    ("Yahoo", "https://news.yahoo.co.jp/rss/topics/world.xml"),     # Yahoo!ニュース 国際
    # 世界情勢（ブルームバーグ・ロイターの日本語記事）
    ("Reuters", google_news_rss("site:jp.reuters.com when:3d")),
    ("Bloomberg", google_news_rss("ブルームバーグ when:3d")),
    # ↓ 一般の主要ニュース（事件・政治なども）を見たい場合は行頭の # を外す。
    # ("NHK", "https://www3.nhk.or.jp/rss/news/cat0.xml"),
    # ("Yahoo", "https://news.yahoo.co.jp/rss/topics/top-picks.xml"),
]

# Googleニュース経由のフィードは、本当にその媒体の記事だけを残すための照合語（小文字）。
SOURCE_FILTER = {"Reuters": "reuters", "Bloomberg": "bloomberg"}

# 出典バッジの色分け用クラス。
BADGE_CLASS = {"NHK": "nhk", "Yahoo": "yahoo", "Reuters": "reuters", "Bloomberg": "bloomberg"}

# 株と無関係なので除外する見出し（株価ページ・スポーツなど）。
SKIP_TITLE = (
    "Stock Price", "Quote", "- NASDAQ", "- NYSE",
    "NBA", "MLB", "プロ野球", "野球", "サッカー", "ゴルフ", "テニス",
    "五輪", "オリンピック", "Jリーグ", "Ｊリーグ", "ラグビー", "相撲",
)


# ====================================================================
# ② カテゴリ分け。見出しに含まれる「キーワード」で自動振り分けします。
#    1つの記事が複数カテゴリに入ることもあります（例：日銀の決定→為替にも）。
# ====================================================================
CATEGORIES = [
    {
        "key": "us",
        "title": "アメリカ・世界（市場・情勢）",
        "emoji": "🌎",
        "keywords": [
            "米", "アメリカ", "ダウ", "ナスダック", "S&P", "NYSE", "NY株", "ウォール街",
            "FRB", "FOMC", "パウエル", "米国", "米株", "利上げ", "利下げ", "米金利",
            "米経済", "米景気", "中国", "欧州", "ECB", "ドイツ", "原油", "世界経済",
            "トランプ", "関税", "半導体", "エヌビディア", "NVIDIA", "アップル", "テスラ",
            "中東", "イラン", "イスラエル", "ウクライナ", "ロシア", "地政学", "情勢", "国連",
        ],
    },
    {
        "key": "jp",
        "title": "日本経済・日銀",
        "emoji": "🇯🇵",
        "keywords": [
            "日銀", "日本銀行", "金融政策", "政策金利", "金利", "物価", "消費者物価",
            "景気", "GDP", "植田", "国債", "日経平均", "東証", "賃上げ", "経済対策",
            "インフレ", "デフレ", "緩和", "利上げ", "マイナス金利",
        ],
    },
    {
        "key": "fx",
        "title": "為替（ドル円）",
        "emoji": "💱",
        "keywords": [
            "円相場", "ドル円", "為替", "円安", "円高", "外国為替", "為替介入",
            "ユーロ円", "対ドル", "円高ドル安", "円安ドル高",
        ],
    },
    {
        "key": "corp",
        "title": "企業・個別株",
        "emoji": "🏢",
        "keywords": [
            "決算", "最高益", "増益", "減益", "営業利益", "純利益", "売上高", "業績",
            "上方修正", "下方修正", "自社株買い", "増配", "減配", "配当", "買収",
            "TOB", "上場", "新製品", "リコール", "提携", "出資", "新工場", "値上げ",
            "トヨタ", "ソニー", "任天堂", "ソフトバンク",
        ],
    },
]


# ====================================================================
# ③ 上部の相場サマリーで表示する指標（yfinance のシンボル）
# ====================================================================
MARKET = [
    ("^N225", "日経平均"),
    ("USDJPY=X", "ドル円"),
    ("^DJI", "NYダウ"),
    ("^IXIC", "ナスダック"),
    ("^GSPC", "S&P500"),
    ("^VIX", "VIX(恐怖指数)"),
]


# --------------------------------------------------------------------
# ニュース取得まわり
# --------------------------------------------------------------------
def fetch_feed(source, url):
    """1つのRSSを読み込み、記事のリストに整える。失敗しても空リストを返す。"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kabu-news/1.0"}
    items = []
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"  ! 取得失敗 [{source}] {url}: {e}")
        return items

    expect = SOURCE_FILTER.get(source)  # Googleニュース経由なら媒体名で絞り込む
    for e in parsed.entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not title or not link:
            continue
        # Googleニュース経由は、目的の媒体（ロイター/ブルームバーグ）の記事だけ残す
        if expect:
            actual = ""
            try:
                actual = (e.source.get("title") or "")
            except Exception:
                actual = ""
            if expect not in actual.lower():
                continue
            # 見出し末尾の「 - 媒体名」を取り除いて読みやすく
            for suf in (" - Reuters", " - Bloomberg.com", " - Bloomberg"):
                if title.endswith(suf):
                    title = title[: -len(suf)]
                    break
        # スポーツや株価ページなど、株と無関係な見出しは除外
        if any(s in title for s in SKIP_TITLE):
            continue
        # 公開日時（UTC）→ 日本時間へ変換。取れなければ None。
        dt = None
        tm = e.get("published_parsed") or e.get("updated_parsed")
        if tm:
            try:
                dt = datetime(*tm[:6], tzinfo=timezone.utc).astimezone(JST)
            except Exception:
                dt = None
        items.append({"title": title, "link": link, "source": source, "dt": dt})
    return items


def collect_news():
    """全RSSを集めて、重複を除き、新しい順に並べる。"""
    all_items = []
    for source, url in FEEDS:
        all_items.extend(fetch_feed(source, url))

    # リンクURLで重複を除去
    seen = set()
    unique = []
    for it in all_items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        unique.append(it)

    # 日時がある記事を新しい順に。日時不明は末尾へ。
    unique.sort(key=lambda x: x["dt"] or datetime(1970, 1, 1, tzinfo=JST), reverse=True)
    return unique


def classify(title):
    """見出しからカテゴリのkeyの集合を返す（複数可）。"""
    hit = set()
    for cat in CATEGORIES:
        for kw in cat["keywords"]:
            if kw in title:
                hit.add(cat["key"])
                break
    return hit


# --------------------------------------------------------------------
# 相場サマリー（yfinance）。入っていない／失敗しても全体は止めない。
# --------------------------------------------------------------------
def market_snapshot():
    rows = []
    try:
        import yfinance as yf
    except Exception:
        print("  ! yfinance が見つからないため相場サマリーは省略します。")
        return rows

    for sym, name in MARKET:
        try:
            df = yf.Ticker(sym).history(period="6mo")[["Open", "High", "Low", "Close"]].dropna()
            if len(df) < 2:
                continue
            # ローソク足用に (始値, 高値, 安値, 終値) の列を作る
            ohlc = [(float(o), float(h), float(l), float(c))
                    for o, h, l, c in zip(df["Open"], df["High"], df["Low"], df["Close"])]
            latest = ohlc[-1][3]
            prev = ohlc[-2][3]
            chg = (latest / prev - 1.0) * 100.0
            rows.append({"name": name, "value": latest, "chg": chg,
                         "ohlc": ohlc, "dates": list(df.index)})  # 区切り線用に日付も保持
        except Exception as e:
            print(f"  ! 相場取得失敗 {name} ({sym}): {e}")
    return rows


# --------------------------------------------------------------------
# 表示用の小さなヘルパー
# --------------------------------------------------------------------
def jp_relative(dt, now):
    if dt is None:
        return ""
    sec = (now - dt).total_seconds()
    if sec < 0:
        sec = 0
    if sec < 3600:
        return f"{int(sec // 60)}分前"
    if sec < 86400:
        return f"{int(sec // 3600)}時間前"
    return f"{int(sec // 86400)}日前"


def fmt_time(dt, now):
    if dt is None:
        return "--"
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%m/%d %H:%M")


def candlestick_svg(ohlc, dates, w=480, h=150, pad=8):
    """OHLC（始値・高値・安値・終値）の列から、ローソク足チャート(SVG)を作る。
    ・日本式の色：陽線（終値≧始値）＝赤、陰線（終値＜始値）＝青（色はCSS変数）。
    ・横線で値（価格・指数）の目盛り＋開始からの％、縦線で月の区切りを表示。
    ・横幅は100%に伸縮し、高さはCSSで固定。外部ライブラリ・ネット不要。"""
    n = min(len(ohlc), len(dates))
    if n < 2:
        return '<div class="spark-empty">データなし</div>'
    ohlc, dates = ohlc[:n], dates[:n]
    lo = min(d[2] for d in ohlc)   # 全体の安値
    hi = max(d[1] for d in ohlc)   # 全体の高値
    rng = (hi - lo) or 1.0
    first = ohlc[0][3]             # 期間の最初の終値（％の基準）
    slot = (w - 2 * pad) / n
    bw = max(slot * 0.62, 0.9)     # ローソクの胴体の幅

    def yy(v):
        return pad + (h - 2 * pad) * (1 - (v - lo) / rng)

    def cx(i):
        return pad + slot * (i + 0.5)

    def fmt_val(v):
        a = abs(v)
        if a >= 1000:
            return f"{v:,.0f}"
        if a >= 100:
            return f"{v:,.1f}"
        return f"{v:,.2f}"

    # 横の目盛り：高値・中間・安値の3本（値＋開始からの％）
    levels = [hi, (hi + lo) / 2.0, lo]
    hgrid = [
        f'<line x1="{pad:.1f}" y1="{yy(v):.1f}" x2="{w - pad:.1f}" y2="{yy(v):.1f}" '
        f'style="stroke:var(--line)" stroke-width="1" '
        f'vector-effect="non-scaling-stroke" stroke-dasharray="1 4" />'
        for v in levels
    ]
    vlabels = "".join(
        f'<span class="lv" style="top:{(yy(v) / h) * 100:.1f}%">{fmt_val(v)}'
        f'<span class="vp">{(v / first - 1.0) * 100:+.1f}%</span></span>'
        for v in levels
    )

    # 縦の区切り：月の変わり目
    ticks = []  # (x座標, ラベル)
    last_ym = None
    for i, d in enumerate(dates):
        ym = (d.year, d.month)
        if ym != last_ym:
            last_ym = ym
            ticks.append((cx(i), f"{d.month}月"))
    vgrid = [
        f'<line x1="{x:.1f}" y1="{pad:.1f}" x2="{x:.1f}" y2="{h - pad:.1f}" '
        f'style="stroke:var(--line)" stroke-width="1" '
        f'vector-effect="non-scaling-stroke" stroke-dasharray="2 3" />'
        for x, _ in ticks
    ]

    bars = []
    for i, (o, high, low, c) in enumerate(ohlc):
        x = cx(i)
        col = "var(--up)" if c >= o else "var(--down)"
        # ヒゲ（高値〜安値）
        bars.append(
            f'<line x1="{x:.1f}" y1="{yy(high):.1f}" x2="{x:.1f}" y2="{yy(low):.1f}" '
            f'style="stroke:{col}" stroke-width="1" vector-effect="non-scaling-stroke" />'
        )
        # 胴体（始値〜終値）
        top = yy(max(o, c))
        bh = max(yy(min(o, c)) - top, 0.9)
        bars.append(
            f'<rect x="{x - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
            f'height="{bh:.1f}" style="fill:{col}" />'
        )

    svg = (
        f'<svg class="candle" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(hgrid)}{"".join(vgrid)}{"".join(bars)}</svg>'
    )
    axis = '<div class="axis">' + "".join(
        f'<span style="left:{(x / w) * 100:.1f}%">{lbl}</span>' for x, lbl in ticks
    ) + "</div>"
    return f'<div class="chart-wrap">{svg}<div class="vaxis">{vlabels}</div></div>' + axis


# --------------------------------------------------------------------
# HTMLを組み立てる
# --------------------------------------------------------------------
def build_html(news, market, now, refresh_min=0, cloud=False):
    esc = html.escape

    # --- 相場サマリー（指標カード＋ローソク足チャート）---
    tiles = []
    for m in market:
        # 前日比の色（日本式：上昇＝赤、下落＝青）
        if m["chg"] > 0:
            cls, arrow = "up", "▲"
        elif m["chg"] < 0:
            cls, arrow = "down", "▼"
        else:
            cls, arrow = "flat", "→"
        chart = candlestick_svg(m.get("ohlc") or [], m.get("dates") or [])
        tiles.append(
            f'<div class="chart-card">'
            f'<div class="c-head"><span class="c-name">{esc(m["name"])}</span>'
            f'<span class="c-chg {cls}">{arrow} {m["chg"]:+.2f}%</span></div>'
            f'<div class="c-value">{m["value"]:,.2f}</div>'
            f"{chart}</div>"
        )
    if tiles:
        snapshot_html = (
            '<div class="snapshot-title">主要指標 ・ ローソク足（直近6か月・日足）'
            '（<span style="color:var(--up);font-weight:700;">赤＝陽線（上昇）</span> / '
            '<span style="color:var(--down);font-weight:700;">青＝陰線（下落）</span>）'
            ' ／ ％は前日比</div>'
            f'<div class="snapshot">{"".join(tiles)}</div>'
        )
    else:
        snapshot_html = '<div class="snapshot-empty">（相場データは取得できませんでした）</div>'

    # --- 各記事をカテゴリへ振り分け ---
    buckets = {cat["key"]: [] for cat in CATEGORIES}
    others = []
    for it in news:
        hits = classify(it["title"])
        if hits:
            for k in hits:
                buckets[k].append(it)
        else:
            others.append(it)

    def render_items(items, limit=25):
        if not items:
            return '<div class="empty">該当するニュースは今ありません。</div>'
        out = []
        for it in items[:limit]:
            badge = BADGE_CLASS.get(it["source"], "other")
            rel = jp_relative(it["dt"], now)
            rel_html = f'<span class="rel">{rel}</span>' if rel else ""
            out.append(
                '<a class="item" href="{link}" target="_blank" rel="noopener">'
                '<div class="meta"><span class="time">{time}</span>'
                '<span class="badge {badge}">{src}</span>{rel}</div>'
                '<div class="title">{title}</div></a>'.format(
                    link=esc(it["link"]),
                    time=fmt_time(it["dt"], now),
                    badge=badge,
                    src=esc(it["source"]),
                    rel=rel_html,
                    title=esc(it["title"]),
                )
            )
        return "".join(out)

    # --- カテゴリのカード ---
    cards = []
    for cat in CATEGORIES:
        items = buckets[cat["key"]]
        cards.append(
            '<section class="card">'
            f'<h2>{cat["emoji"]} {esc(cat["title"])}'
            f'<span class="count">{len(items)}</span></h2>'
            f'<div class="list">{render_items(items)}</div>'
            "</section>"
        )
    # その他
    cards.append(
        '<section class="card">'
        f'<h2>📰 その他の経済・国際ニュース<span class="count">{len(others)}</span></h2>'
        f'<div class="list">{render_items(others)}</div>'
        "</section>"
    )

    now_str = now.strftime("%Y-%m-%d %H:%M")

    # 自動更新の表示。cloud=クラウド自動更新 / refresh_min>0=PC常駐 / それ以外=単発
    if cloud:
        refresh_meta = f'<meta http-equiv="refresh" content="{refresh_min * 60}">'
        refresh_note = f' ・ 約{refresh_min}分ごとに自動更新（クラウド）'
        refresh_footer = (
            f'この画面はクラウド上で約 <b>{refresh_min}分ごと</b>に自動更新されます'
            '（PCの電源が切れていても更新されます）。'
        )
    elif refresh_min > 0:
        refresh_meta = f'<meta http-equiv="refresh" content="{refresh_min * 60}">'
        refresh_note = f' ・ <b>{refresh_min}分ごとに自動更新</b>'
        refresh_footer = (
            f'この画面は <b>{refresh_min}分ごと</b>に自動で最新へ更新されます。'
            '更新を止めるには、起動した黒いウィンドウを閉じてください。'
        )
    else:
        refresh_meta = ""
        refresh_note = ""
        refresh_footer = (
            '最新にするには、デスクトップの「株ニュース」'
            '（<code>start.bat</code>）をもう一度実行してください。'
        )

    return PAGE_TEMPLATE.format(
        now=now_str,
        snapshot=snapshot_html,
        cards="".join(cards),
        total=len(news),
        refresh_meta=refresh_meta,
        refresh_note=refresh_note,
        refresh_footer=refresh_footer,
    )


# HTMLのひな型（CSSは中括弧が多いので {{ }} でエスケープ済み）
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
{refresh_meta}
<title>日本株ニュース・ダッシュボード</title>
<style>
  :root {{
    --up:#f0665f; --down:#5aa0f2; --bg:#060709; --card:#121417;
    --ink:#e6ecf4; --sub:#9098a6; --line:#262b32; --navy:#2f6fb0;
    --shadow:0 2px 10px rgba(0,0,0,.6); --cardborder:1px solid #23272e;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:system-ui,"Segoe UI","Hiragino Kaku Gothic ProN","Meiryo",sans-serif;
    line-height:1.5; }}
  header {{ background:linear-gradient(135deg,#0a1018,#13243c); color:#fff;
    padding:18px 22px; }}
  header h1 {{ margin:0; font-size:20px; }}
  header .sub {{ margin-top:4px; font-size:12.5px; opacity:.85; }}
  .wrap {{ max-width:1500px; margin:0 auto; padding:18px 22px 40px; }}
  /* 相場サマリー */
  .snapshot-title {{ font-size:12.5px; color:var(--sub); margin:2px 0 9px; }}
  .snapshot {{ display:grid; gap:14px; margin:0 0 22px;
    grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }}
  .chart-card {{ background:var(--card); border-radius:12px; padding:11px 14px 8px;
    box-shadow:var(--shadow); border:var(--cardborder); }}
  .c-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:6px; }}
  .c-name {{ font-size:13px; color:var(--sub); font-weight:600; }}
  .c-chg {{ font-size:12.5px; font-weight:700; white-space:nowrap; }}
  .c-chg.up {{ color:var(--up); }}
  .c-chg.down {{ color:var(--down); }}
  .c-chg.flat {{ color:var(--sub); }}
  .c-value {{ font-size:20px; font-weight:700; margin:1px 0 6px; }}
  .chart-wrap {{ position:relative; }}
  .candle {{ width:100%; height:150px; display:block; }}
  .vaxis {{ position:absolute; top:0; right:0; bottom:0; left:0; pointer-events:none; }}
  .vaxis .lv {{ position:absolute; right:3px; transform:translateY(-50%);
    font-size:9.5px; color:var(--ink); background:rgba(18,20,23,.74);
    padding:0 4px; border-radius:3px; white-space:nowrap; }}
  .vaxis .vp {{ color:var(--sub); margin-left:4px; }}
  .axis {{ position:relative; height:14px; margin-top:4px; }}
  .axis span {{ position:absolute; transform:translateX(-50%); white-space:nowrap;
    font-size:10px; color:var(--sub); }}
  .spark-empty {{ height:150px; display:flex; align-items:center; justify-content:center;
    color:var(--sub); font-size:12px; }}
  .snapshot-empty {{ color:var(--sub); font-size:13px; margin-bottom:18px; }}
  /* カードのグリッド */
  .grid {{ display:grid; gap:16px;
    grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); }}
  .card {{ background:var(--card); border-radius:14px; overflow:hidden;
    box-shadow:var(--shadow); border:var(--cardborder); display:flex; flex-direction:column; }}
  .card h2 {{ margin:0; padding:13px 16px; font-size:15px;
    border-bottom:2px solid var(--line); display:flex; align-items:center;
    justify-content:space-between; background:#191f29; }}
  .count {{ font-size:12px; font-weight:600; color:#fff; background:var(--navy);
    border-radius:999px; padding:1px 9px; }}
  .list {{ padding:4px 16px 10px; overflow-y:auto; max-height:74vh; }}
  .item {{ display:block; text-decoration:none; color:inherit;
    padding:10px 0; border-bottom:1px solid var(--line); }}
  .item:last-child {{ border-bottom:none; }}
  .item:hover .title {{ text-decoration:underline; color:var(--down); }}
  .meta {{ display:flex; align-items:center; gap:8px; margin-bottom:3px; }}
  .time {{ font-size:11.5px; color:var(--sub); }}
  .rel {{ font-size:11px; color:#9aa1ab; }}
  .badge {{ font-size:10.5px; font-weight:700; border-radius:5px; padding:1px 6px; }}
  .badge.nhk {{ background:rgba(90,160,242,.20); color:#9ec5f5; }}
  .badge.yahoo {{ background:rgba(240,102,95,.20); color:#f4a39d; }}
  .badge.reuters {{ background:rgba(244,140,60,.20); color:#f3b487; }}
  .badge.bloomberg {{ background:rgba(255,255,255,.16); color:#eef2f7; }}
  .badge.other {{ background:rgba(255,255,255,.08); color:#aab4c2; }}
  .title {{ font-size:14px; }}
  .empty {{ color:var(--sub); font-size:13px; padding:14px 0; }}
  footer {{ max-width:1500px; margin:0 auto; padding:0 22px 30px;
    color:var(--sub); font-size:12px; }}
  footer code {{ background:rgba(255,255,255,.12); color:#dbe3ee; padding:1px 6px; border-radius:5px; }}
</style>
</head>
<body>
<header>
  <h1>📊 日本株ニュース・ダッシュボード</h1>
  <div class="sub">最終更新：{now}（日本時間）／ 記事 {total} 件 ・ 出典：NHK / Yahoo!ニュース ・ 相場：yfinance{refresh_note}</div>
</header>
<div class="wrap">
  {snapshot}
  <div class="grid">
    {cards}
  </div>
</div>
<footer>
  色は日本式（<span style="color:var(--up);font-weight:700;">赤＝上昇</span> /
  <span style="color:var(--down);font-weight:700;">青＝下落</span>）。見出しをクリックすると元記事が開きます。<br>
  {refresh_footer}
</footer>
</body>
</html>
"""


def build_once(open_browser, refresh_min, cloud=False):
    """1回ぶんの「取得 → HTML生成 → 保存」。最初の1回だけブラウザを開く。"""
    now = datetime.now(JST)
    print(f"［{now.strftime('%H:%M')}］ニュースを取得中...")
    news = collect_news()
    print(f"  → ニュース {len(news)} 件")

    print("相場データを取得中...")
    market = market_snapshot()
    print(f"  → 相場 {len(market)} 件")

    html_text = build_html(news, market, now, refresh_min=refresh_min, cloud=cloud)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"  → 画面を更新しました: {out_path}")

    if open_browser:
        try:
            webbrowser.open("file:///" + out_path.replace("\\", "/"))
            print("  → ブラウザで開きました。")
        except Exception as e:
            print(f"  ! ブラウザを開けませんでした: {e}")


def main():
    cloud = "--cloud" in sys.argv        # クラウド(GitHub Actions)用：1回生成＋自動更新メタ付き
    once = "--once" in sys.argv          # 1回だけ実行して終了（自動更新しない）
    open_browser = "--no-open" not in sys.argv

    if cloud:
        build_once(open_browser=False, refresh_min=CLOUD_REFRESH_MIN, cloud=True)
        print("\n(cloud) 完了です。")
        return

    if once:
        build_once(open_browser, refresh_min=0)
        print("\n完了です。")
        return

    print("=" * 56)
    print(f" 自動更新モード：{REFRESH_MIN}分ごとに最新へ更新します。")
    print(" 終了するには、このウィンドウを閉じてください。")
    print("=" * 56 + "\n")
    first = True
    try:
        while True:
            build_once(open_browser and first, refresh_min=REFRESH_MIN)
            first = False
            print(f"  …次の更新まで {REFRESH_MIN} 分待機中（このまま開いておいてください）\n")
            time.sleep(REFRESH_MIN * 60)
    except KeyboardInterrupt:
        print("\n終了しました。")


if __name__ == "__main__":
    main()
