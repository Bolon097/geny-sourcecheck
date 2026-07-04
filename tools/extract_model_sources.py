#!/usr/bin/env python3
"""Extract and deduplicate source references from the comparison dashboard."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "三模型横向对比Dashboard_单文件版.html"
OUTPUT = ROOT / "三模型全部链接与数据来源核查清单.md"

LEVEL_NAMES = {"P1": "简单版", "P2": "中等版", "P3": "难版"}
MODEL_NAMES = {"GPT": "GPT", "Claude": "Claude", "DeepSeek": "DeepSeek"}

SOURCE_ALIASES = {
    "杭州市人民政府门户网站": ("杭州市人民政府门户网站", "杭州市政府网", "杭州政府网"),
    "杭州数据开放平台": ("杭州数据开放平台", "杭州市数据开放平台", "杭州市公共数据开放平台"),
    "浙江省公共数据开放平台": ("浙江省公共数据开放平台", "浙江政务服务网", "浙江公共数据开放平台"),
    "杭州市城乡建设委员会": ("杭州市城乡建设委员会", "杭州市建委", "杭州市城建委", "市建委"),
    "杭州市发展和改革委员会": ("杭州市发展和改革委员会", "杭州市发改委", "市发改委"),
    "杭州市交通运输局": ("杭州市交通运输局", "杭州交通运输局"),
    "杭州市统计局": ("杭州市统计局", "杭州统计局"),
    "西湖区充电基础设施布局规划 PDF": (
        "西湖区充电基础设施布局规划",
        "西湖区规划PDF",
        "西湖区规划 PDF",
    ),
    "杭州停车 / 一键找桩": ("杭州停车", "一键找桩"),
    "杭州 e 充": ("杭州e充", "杭州 e 充"),
    "高德地图 / 高德开放平台": ("高德地图", "高德开放平台", "高德 API", "高德/"),
    "百度地图 / 百度地图开放平台": ("百度地图", "百度地图开放平台", "百度 API", "百度/"),
    "腾讯地图": ("腾讯地图", "腾讯地图 API"),
    "OpenStreetMap / Overpass API": ("OpenStreetMap", "Overpass API", "OSM"),
    "中国电动汽车充电基础设施促进联盟 / 中国充电联盟": (
        "中国电动汽车充电基础设施促进联盟",
        "中国充电联盟",
        "充电联盟",
    ),
    "国家电网 / e充电": ("国家电网", "e充电", "e 充电"),
    "特来电": ("特来电",),
    "星星充电": ("星星充电",),
    "云快充": ("云快充",),
    "小桔充电": ("小桔充电",),
    "浙江在线 / 潮新闻": ("浙江在线", "潮新闻", "Zhejiang News"),
    "杭州网": ("杭州网", "Hangzhou Forum"),
    "杭州日报": ("杭州日报",),
    "杭州发布": ("杭州发布",),
    "新华网": ("新华网",),
    "第一电动网": ("第一电动网",),
    "电车资源": ("电车资源",),
    "汽车之家 / icauto 充电站目录": ("icauto", "汽车之家"),
    "城市吧 / city8": ("city8", "城市吧"),
    "微信公众号 / 微信文章": ("微信公众号", "微信文章", "微信"),
    "运营商 App / 小程序": ("运营商APP", "运营商 App", "运营商小程序"),
}

EXCLUDED_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
}
SOURCE_COLUMN_HEADINGS = {
    "主要证据来源",
    "可能来源",
    "推荐数据源",
    "推荐来源",
    "数据来源",
    "数据来源/来源类型",
    "数据源",
    "来源",
    "来源名称",
    "来源链接",
    "现有可用来源",
    "直接提取来源",
    "证据来源",
}

ARTICLE_RE = re.compile(
    r'<article class="card" data-model="(?P<model>[^"]+)" '
    r'data-sq="(?P<sq>[^"]+)" data-level="(?P<level>[^"]+)"[^>]*>'
    r"(?P<body>.*?)</article>",
    re.S,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
TAG_RE = re.compile(r"<[^>]+>")


class TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def decode_repeatedly(value: str) -> str:
    for _ in range(4):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


def clean_url(raw: str) -> str | None:
    url = decode_repeatedly(raw).strip()
    url = re.split(r"[（）：）【】《》。，；！？、“”]|(?:\]\()", url, maxsplit=1)[0]
    url = url.rstrip("`*.,;:!?，。；：！？、)]}）】》")
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = parts.netloc.lower()
    if not host or host in EXCLUDED_HOSTS:
        return None
    path = parts.path or ""
    if path == "/":
        path = ""
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, parts.fragment))


def plain_text(fragment: str) -> str:
    text = decode_repeatedly(fragment)
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def usage_label(model: str, level: str, sq: str) -> str:
    return f"{MODEL_NAMES.get(model, model)}{LEVEL_NAMES.get(level, level)}({level}) {sq}"


def markdown_link(url: str) -> str:
    return f"[点击打开来源]({url})  \n`{url}`"


def main() -> None:
    dashboard = INPUT.read_text(encoding="utf-8")
    url_usage: dict[str, set[str]] = defaultdict(set)
    source_usage: dict[str, set[str]] = defaultdict(set)
    source_field_usage: dict[str, set[str]] = defaultdict(set)
    cards = 0

    for match in ARTICLE_RE.finditer(dashboard):
        cards += 1
        label = usage_label(match["model"], match["level"], match["sq"])
        decoded_body = decode_repeatedly(match["body"])
        text = plain_text(match["body"])

        for raw_url in URL_RE.findall(decoded_body):
            url = clean_url(raw_url)
            if url:
                url_usage[url].add(label)

        for source_name, aliases in SOURCE_ALIASES.items():
            if any(alias.lower() in text.lower() for alias in aliases):
                source_usage[source_name].add(label)

        table_extractor = TableExtractor()
        table_extractor.feed(decoded_body)
        for table in table_extractor.tables:
            if len(table) < 2:
                continue
            source_columns = [
                index
                for index, heading in enumerate(table[0])
                if heading.strip() in SOURCE_COLUMN_HEADINGS or heading.strip().lower() == "source"
            ]
            for row in table[1:]:
                for index in source_columns:
                    if index >= len(row):
                        continue
                    value = re.sub(r"\s+", " ", row[index]).strip(" -|")
                    if (
                        not value
                        or len(value) > 180
                        or value.lower() in {"无", "暂无", "未提供", "同上", "..."}
                        or re.fullmatch(r"\d{4}(?:[-–]\d{2}){0,2}(?:规划)?", value)
                        or re.match(r"^SQ\d", value, re.I)
                    ):
                        continue
                    if URL_RE.fullmatch(value):
                        continue
                    source_field_usage[value].add(label)

    merged_urls: dict[tuple[str, str, str, str], tuple[str, set[str]]] = {}
    for url, labels in url_usage.items():
        parts = urlsplit(url)
        key = (parts.netloc, parts.path.rstrip("/"), parts.query, parts.fragment)
        if key not in merged_urls:
            merged_urls[key] = (url, set(labels))
            continue
        preferred, combined_labels = merged_urls[key]
        if parts.scheme == "https" and urlsplit(preferred).scheme != "https":
            preferred = url
        combined_labels.update(labels)
        merged_urls[key] = (preferred, combined_labels)
    url_usage = {url: labels for url, labels in merged_urls.values()}

    lines = [
        "# 三模型全部链接与数据来源核查清单",
        "",
        f"- 来源文件：`{INPUT.name}`",
        f"- 覆盖范围：{cards} 组输出（GPT、Claude、DeepSeek；简单版、中等版、难版；SQ1-SQ6）",
        f"- 去重后可点击链接：{len(url_usage)} 条",
        f"- 归并后的无精确链接来源/平台：{len(source_usage)} 类",
        f"- 来源字段原文条目：{len(source_field_usage)} 条",
        "- 说明：同一链接只列一次；“使用位置”合并列出所有提到该链接的模型、难度和 SQ。",
        "- 说明：已排除 Dashboard 自身使用的 Chart.js、图标字体等前端资源链接。",
        "- 说明：Dashboard 中模型名为 `Claude`；本文按该名称整理。",
        "",
        "## A. 去重后的可点击链接",
        "",
    ]

    for index, url in enumerate(sorted(url_usage, key=lambda item: (urlsplit(item).netloc, item)), 1):
        labels = "，".join(sorted(url_usage[url]))
        lines.extend(
            [
                f"### A{index:03d}",
                f"**使用位置：** {labels}",
                "",
                markdown_link(url),
                "",
                "- [ ] 已人工打开核查",
                "- [ ] 来源有效且与引用内容一致",
                "",
            ]
        )

    lines.extend(
        [
            "## B. 提到但未必给出精确页面链接的数据来源/平台",
            "",
            "这一部分用于补充模型只写来源名称、平台名、App、小程序或报告名，但没有提供可直接打开的 page-level URL 的情况。",
            "",
        ]
    )
    for index, source in enumerate(sorted(source_usage), 1):
        labels = "，".join(sorted(source_usage[source]))
        lines.extend(
            [
                f"### B{index:03d} · {source}",
                f"**提到位置：** {labels}",
                "",
                "- [ ] 已找到并核查对应官方页面/文件",
                "",
            ]
        )

    lines.extend(
        [
            "## C. 输出表格中“来源 / 数据源 / Source”列的原文条目",
            "",
            "本节保留模型表格里的来源字段原文，以捕捉报告名、新闻名、平台名及不完整引用。相同原文已合并；近义写法未强行合并，便于回到原输出核查。",
            "",
        ]
    )
    for index, source in enumerate(sorted(source_field_usage), 1):
        labels = "，".join(sorted(source_field_usage[source]))
        lines.extend(
            [
                f"### C{index:03d}",
                f"**提到位置：** {labels}",
                "",
                source,
                "",
                "- [ ] 已核查原文来源",
                "",
            ]
        )

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"cards={cards}")
    print(f"unique_urls={len(url_usage)}")
    print(f"named_sources={len(source_usage)}")
    print(f"source_field_entries={len(source_field_usage)}")
    print(f"output={OUTPUT}")


if __name__ == "__main__":
    main()
