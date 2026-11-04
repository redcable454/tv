#!/usr/bin/env python3
"""Importa la parrilla diaria publicada por TV360 Bitel para Bicolor+."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
URL = "https://tv360.bitel.com.pe/tv/bicolor?ch=709"
CHANNEL_ID = "bicolor-teleclub"
TZ = ZoneInfo("America/Lima")

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.lines.append(text)

def main():
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0 TeleclubTV-EPG/1.0"})
    with urlopen(req, timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    parser = TextExtractor()
    parser.feed(html)
    lines = parser.lines

    events = []
    for i, line in enumerate(lines):
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", line)
        if not m:
            continue
        title = next((x for x in lines[i+1:i+5] if x and not re.fullmatch(r"(\d{1,2}):(\d{2})", x)), "")
        if not title or title.lower() in {"programación", "hoy", "bicolor+", "todas"}:
            continue
        # La parrilla de Bitel presenta títulos en mayúsculas; evitar fechas y controles.
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", title):
            continue
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            continue
        events.append((hour * 60 + minute, title))

    # Quitar duplicados consecutivos causados por elementos responsive del HTML.
    deduped = []
    for event in events:
        if not deduped or deduped[-1] != event:
            deduped.append(event)
    events = deduped
    if len(events) < 2:
        print(f"AVISO: TV360 no expuso una parrilla legible (eventos={len(events)}); se conserva el XML sin inventar programas."); return

    root = ET.parse(EPG).getroot()
    if not any(ch.attrib.get("id") == CHANNEL_ID for ch in root.findall("channel")):
        raise SystemExit(f"No existe el canal XMLTV {CHANNEL_ID}; XML sin modificar.")

    today = datetime.now(TZ).date()
    existing = [p for p in root.findall("programme") if p.attrib.get("channel") == CHANNEL_ID]
    for p in existing:
        root.remove(p)

    for idx, (start_min, title) in enumerate(events):
        if idx + 1 < len(events):
            end_min = events[idx + 1][0]
        else:
            end_min = start_min + 150
        if end_min <= start_min:
            continue
        start = datetime.combine(today, datetime.min.time(), TZ) + timedelta(minutes=start_min)
        stop = datetime.combine(today, datetime.min.time(), TZ) + timedelta(minutes=end_min)
        p = ET.Element("programme", {
            "start": start.strftime("%Y%m%d%H%M%S %z"),
            "stop": stop.strftime("%Y%m%d%H%M%S %z"),
            "channel": CHANNEL_ID,
        })
        ET.SubElement(p, "title", {"lang": "es"}).text = title
        ET.SubElement(p, "category", {"lang": "es"}).text = "Deportes"
        root.append(p)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"EPG Bicolor+ ({CHANNEL_ID}): {len(events)} programas importados desde TV360 para {today.isoformat()}.")

if __name__ == "__main__":
    main()
