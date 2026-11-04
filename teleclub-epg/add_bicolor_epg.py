#!/usr/bin/env python3
"""Importa las parrillas publicadas por TV360 Bitel para los canales Bicolor+."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
CHANNELS = (
    ("https://tv360.bitel.com.pe/tv/bicolor?ch=709", "bicolor-teleclub", "Bicolor+"),
    ("https://tv360.bitel.com.pe/tv/bicolor-premium?ch=704", "bicolor-premium.teleclub", "Bicolor+ Premium"),
)
TZ = ZoneInfo("America/Lima")

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.lines.append(value)

def read_events(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 TeleclubTV-EPG/1.0"})
    with urlopen(req, timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    parser = TextExtractor()
    parser.feed(html)
    lines = parser.lines
    events = []
    for i, line in enumerate(lines):
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", line)
        if not match:
            continue
        title = next((x for x in lines[i+1:i+5] if x and not re.fullmatch(r"(\d{1,2}):(\d{2})", x)), "")
        if not title or title.lower() in {"programación", "hoy", "bicolor+", "bicolor+ premium", "todas"}:
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", title):
            continue
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            continue
        event = (hour * 60 + minute, title)
        if not events or events[-1] != event:
            events.append(event)
    return events

def main():
    root = ET.parse(EPG).getroot()
    today = datetime.now(TZ).date()
    for url, channel_id, label in CHANNELS:
        try:
            events = read_events(url)
        except Exception as exc:
            print(f"AVISO: no se pudo leer {label} desde TV360 ({exc}); se conserva su XML actual.")
            continue
        if len(events) < 2:
            print(f"AVISO: TV360 no expuso una parrilla legible para {label} (eventos={len(events)}); se conserva el XML actual.")
            continue
        if not any(ch.attrib.get("id") == channel_id for ch in root.findall("channel")):
            print(f"AVISO: no existe el canal XMLTV {channel_id}; no se agregan programas.")
            continue

        for programme in list(root.findall("programme")):
            if programme.attrib.get("channel") == channel_id:
                root.remove(programme)

        imported = 0
        for idx, (start_min, title) in enumerate(events):
            end_min = events[idx + 1][0] if idx + 1 < len(events) else start_min + 150
            if end_min <= start_min:
                continue
            start = datetime.combine(today, datetime.min.time(), TZ) + timedelta(minutes=start_min)
            stop = datetime.combine(today, datetime.min.time(), TZ) + timedelta(minutes=end_min)
            programme = ET.Element("programme", {
                "start": start.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": channel_id,
            })
            ET.SubElement(programme, "title", {"lang": "es"}).text = title
            root.append(programme)
            imported += 1
        print(f"EPG {label} ({channel_id}): {imported} programas importados desde TV360 para {today.isoformat()}.")

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
