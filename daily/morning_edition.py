#!/usr/bin/env python3
"""Generate a source-checked morning edition from an articles.json snapshot."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DAILY = Path(__file__).resolve().parent
RANKER = DAILY / "rank_with_jev.mjs"
MODEL = "gemini-3-flash-preview"
JST = ZoneInfo("Asia/Tokyo")
GTM_HEAD = '''  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
  new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  })(window,document,'script','dataLayer','GTM-NNQDZVDZ');</script>
  <!-- End Google Tag Manager -->
  <script>
    // GTM移行後もJS側の gtag(...) 呼び出しを生かすためのスタブ。
    // 実体は dataLayer.push なので、GTM がそのまま受け取る。
    // ⚠️ これを消すと app.js の typeof ガードが false になり
    //    select_content / select_item が静かに停止する（JSエラーは出ない）。
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
  </script>'''
GTM_NOSCRIPT = '''  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-NNQDZVDZ"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->'''
LATIN_TERM = re.compile(r"(?<![A-Za-z])[A-Z][A-Za-z0-9.+#_-]*(?:\s+[A-Z][A-Za-z0-9.+#_-]*)*")
NUMBER_TERM = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|％|円|ドル|件|本|人|個|倍|年|月|日|時間|分|秒)?")


def fail(message: str) -> "NoReturn":
    print(message.replace("\n", " "), file=sys.stderr)
    raise SystemExit(1)
