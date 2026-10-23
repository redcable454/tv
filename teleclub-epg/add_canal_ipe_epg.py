#!/usr/bin/env python3
"""Importa la programación de Canal IPe desde la página oficial de IRTP al XMLTV.

No inventa horarios: si IRTP cambia el HTML y no se pueden identificar eventos,
conserva la guía actual y termina sin alterar los demás canales.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import json
import re

URL = "https://www.irtpplay.gob.pe/canalipe/programacion"
EPG = Path(__file__).with_name("guia_teleclubtv.xml")
CHANNEL_ID = "ipe.teleclub"
CHANNEL_NAME = "CANAL IPE SD"
MARKER = "Fuente oficial: https://www.irtpplay.gob.pe/canalipe/programacion"
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.]([0-5]\d)\s*(A\.?\s*M\.?|P\.?\s*M\.?)\s*$", re.I)
DAY_RE = re.compile(r"^(lun(?:es)?|mar(?:tes)?|mi[eé](?:rcoles)?|jue(?:ves)?|vie(?:rnes)?|s[aá]b(?:ado)?|dom(?:ingo)?)(?:\s*[,|:]?\s*\d{1,2})?$", re.I)
DAYS = {"lun":0,"mar":1,"mié":2,"mie":2,"jue":3,"vie":4,"sáb":5,"sab":5,"dom":6}

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("br", "p", "div", "li", "article", "section", "h1", "h2", "h3"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "li", "article", "section", "h1", "h2", "h3"):
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)

def parse_time(text):
    m = TIME_RE.match(text or "")
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    pm = m.group(3).upper().startswith("P")
    if hour == 12:
        hour = 0
    if pm:
        hour += 12
    return hour * 60 + minute

def xml_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")

def main():
    if not EPG.exists():
        raise SystemExit(f"No existe XMLTV: {EPG}")
    request = Request(URL, headers={"User-Agent":"Mozilla/5.0 (compatible; TeleclubTV-EPG/1.0)", "Accept":"text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"AVISO: IRTP no permitió descargar la programación de Canal IPe ({exc}); se conserva la guía actual.")
        return

    parser = TextExtractor()
    parser.feed(html)
    lines = [x.strip() for x in "\n".join(parser.parts).splitlines() if x.strip()]

    # La página oficial presenta cada ficha como título, hora y descripción.
    # Solo aceptamos una ficha si se identifica una hora explícita junto a un título.
    events = []
    current_day = None
    for i, line in enumerate(lines):
        day_match = DAY_RE.match(line)
        if day_match:
            prefix = re.match(r"^(lun|mar|mié|mie|jue|vie|sáb|sab|dom)", line.lower())
            if prefix:
                current_day = DAYS.get(prefix.group(1))
        minute = parse_time(line)
        if minute is None or i == 0:
            continue
        title = lines[i - 1].strip()
        if not title or len(title) > 120 or title.lower() in {"programación", "canal ipe", "en vivo"}:
            continue
        if title.lower().startswith(("lun", "mar", "mié", "mie", "jue", "vie", "sáb", "sab", "dom")):
            continue
        events.append({"title": title, "minute": minute, "day": current_day})

    # Remove duplicate card text while preserving order. Never publish a fabricated
    # full-day schedule when the official page structure cannot be parsed.
    unique = []
    seen = set()
    for event in events:
        key = (event["day"], event["minute"], event["title"].casefold())
        if key not in seen:
            seen.add(key)
            unique.append(event)
    if len(unique) < 5:
        print(f"AVISO: solo se detectaron {len(unique)} fichas de Canal IPe en la página oficial; no se modifica su EPG para evitar horarios inventados.")
        return

    tree = ET.parse(EPG)
    root = tree.getroot()
    channel = next((c for c in root.findall("channel") if c.get("id") == CHANNEL_ID), None)
    if channel is None:
        channel = ET.Element("channel", {"id": CHANNEL_ID})
        first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
        root.insert(first_programme, channel)
    names = {(x.text or "").strip().casefold() for x in channel.findall("display-name")}
    if CHANNEL_NAME.casefold() not in names:
        ET.SubElement(channel, "display-name", {"lang":"es"}).text = CHANNEL_NAME

    for item in list(root.findall("programme")):
        if item.get("channel") == CHANNEL_ID and MARKER in (item.findtext("desc") or ""):
            root.remove(item)

    # Schedule page can expose one or more weekday tabs. Use the official
    # day labels when available; if no day is exposed, apply the listed sequence
    # only to today's date, rather than assuming a weekly repeat.
    from datetime import date, time
    from zoneinfo import ZoneInfo
    lima = ZoneInfo("America/Lima")
    today = datetime.now(lima).date()
    has_days = any(e["day"] is not None for e in unique)
    days_to_generate = 7 if has_days else 1
    for offset in range(days_to_generate):
        day = today + timedelta(days=offset)
        day_events = [e for e in unique if (e["day"] == day.weekday() if has_days else True)]
        day_events.sort(key=lambda e:e["minute"])
        for n, event in enumerate(day_events):
            start = datetime.combine(day, time(event["minute"]//60, event["minute"]%60), tzinfo=lima)
            if n + 1 < len(day_events):
                stop_minute = day_events[n+1]["minute"]
                stop = datetime.combine(day, time(stop_minute//60, stop_minute%60), tzinfo=lima)
            else:
                stop = start + timedelta(minutes=30)
            if stop <= start:
                continue
            programme = ET.SubElement(root, "programme", {"start":xml_time(start), "stop":xml_time(stop), "channel":CHANNEL_ID})
            ET.SubElement(programme, "title", {"lang":"es"}).text = event["title"]
            ET.SubElement(programme, "desc", {"lang":"es"}).text = MARKER
            ET.SubElement(programme, "category", {"lang":"es"}).text = "Infantil"

    programmes = root.findall("programme")
    programmes.sort(key=lambda p:(p.get("start",""), p.get("channel","")))
    first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
    for item in programmes:
        root.remove(item)
    for i, item in enumerate(programmes):
        root.insert(first_programme+i, item)
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Canal IPe: añadidas fichas oficiales detectadas={len(unique)}; id={CHANNEL_ID}; días generados={days_to_generate}")

if __name__ == "__main__":
    main()
