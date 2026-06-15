"""Histock 券商分點 adapter（M3-1，§18.4）—— 個別券商分點買賣超的可得 live 來源。

Histock 個股「分公司進出」頁把當日**買超/賣超前 N 大分點**直接放在靜態 HTML 表格
（無需 JS、無 API），含券商名稱 / 買張 / 賣張 / 買賣超 / 均價。外資分點命名帶地緣字樣
（台灣摩根士丹利 / 美林 / 美商高盛 / 新加坡商瑞銀 / 港商野村 / 花旗環球…），剛好對得上
`config/broker_map.json` 的名稱關鍵字 → 推估外資/投信/中實戶（一律標『推估・非確認』）。

`parse_branch` 為純函式（吃 HTML 字串、零網路）方便測試；`fetch` 包成統一 `TargetFlows`。
單日快照：連續買超天數退化為「單日」、無總量時買超佔比為 None（誠實降級）。
Tier B：第三方彙整，數字待證交所/投信核對。
"""
from __future__ import annotations

import html
import re

from ...http import get_bytes
from .base import BrokerFlow, NoData, TargetFlows

URL = "https://histock.tw/stock/branch.aspx?no={code}"
_DATE = re.compile(r"(20\d{2})/(\d{1,2})/(\d{1,2})")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TABLE = re.compile(r"<table[^>]*>.*?</table>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _int(s: str) -> int | None:
    s = (s or "").replace(",", "").strip()
    try:
        return int(s)
    except ValueError:
        return None


def _row_cells(row: str) -> list[str]:
    """保留空白欄（不可過濾，否則買/賣兩側欄位錯位）。"""
    return [html.unescape(_TAG.sub("", c)).strip() for c in _CELL.findall(row)]


def parse_branch(html_text: str, code: str) -> tuple[str | None, list[BrokerFlow]]:
    """純解析：HTML → (資料日 ISO, [BrokerFlow])。賣超側 net 為負、買超側為正。

    逐 <tr> 解析（每列 10 欄：賣超側 5 + 買超側 5），空白欄保留以維持欄位對齊。
    """
    md = _DATE.search(html_text)
    date = f"{md.group(1)}-{int(md.group(2)):02d}-{int(md.group(3)):02d}" if md else None

    block = next((b for b in _TABLE.findall(html_text)
                  if "券商名稱" in b and "買超" in b), None)
    if not block:
        return date, []

    flows: list[BrokerFlow] = []
    skip = ("券商名稱", "合計", "總計", "小計")
    for row in _ROW.findall(block):
        c = _row_cells(row)
        if len(c) < 10:
            continue
        # 賣超側：名稱 c[0]、賣超 c[3]（負）；買超側：名稱 c[5]、買超 c[8]（正）
        for name, net in ((c[0], _int(c[3])), (c[5], _int(c[8]))):
            if name and net is not None and not any(k in name for k in skip):
                flows.append(BrokerFlow(code, date or "", name, name, net))
    return date, flows


def fetch_day(code: str) -> tuple[str, list[BrokerFlow]]:
    """抓 Histock 分點頁、回傳 (資料日, 當日 [BrokerFlow])；無資料 → NoData（誠實降級）。"""
    try:
        raw = get_bytes(URL.format(code=code), cache_ttl=3 * 3600)
    except Exception as e:
        raise NoData(f"Histock 分點取得失敗 {code}：{e}") from e
    date, flows = parse_branch(raw.decode("utf-8", "ignore"), code)
    if not flows or not date:
        raise NoData(f"Histock 無 {code} 分點資料（非上市/當日無揭露）")
    return date, flows


def fetch(code: str) -> TargetFlows:
    """單日 TargetFlows（不累積歷史）；多日窗請走 brokers.load_flows / history。"""
    date, flows = fetch_day(code)
    return TargetFlows(code, code, flows, {}, as_of=date, tier="B")
