#!/usr/bin/env python3
"""Importa la parrilla visible de Canal IPe desde su página oficial de horarios.

Usa canalipe.gob.pe/horarios porque IRTP Play puede devolver 403 a los bots.
No inventa una semana completa: publica solo las fichas horarias que logra leer
de la página oficial y conserva la guía existente si la extracción no es fiable.
"""
from datetime import datetime, timedelta, timezone, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import re
import html as html_lib

URL = "https://www.canalipe.gob.pe/horarios"
EPG = Path(__file__).with_name("guia_teleclubtv.xml")
CHANNEL_ID = "ipe.teleclub"
CHANNEL_NAME = "CANAL IPE SD"
MARKER = "Fuente oficial: https://www.canalipe.gob.pe/horarios"
LIMA = ZoneInfo("America/Lima")
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?:\s*([AP])\.?\s*M\.?)?\s*$", re.I)
SKIP_LINES = {
    "ahora", "image", "imagen", "disponible en: ipe play", "disponible en ipe play",
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo",
}

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if tag in ("br", "p", "div", "li", "article", "section", "h1", "h2", "h3", "h4", "tr", "td", "th"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "li", "article", "section", "h1", "h2", "h3", "h4", "tr", "td", "th"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(html_lib.unescape(data).split())
            if value:
                self.parts.append(value)

def parse_time(text):
    m = TIME_RE.match(text or "")
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    suffix = (m.group(3) or "").upper()
    if suffix:
        if hour == 12:
            hour = 0
        if suffix == "P":
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute

def xml_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")

def main():
    if not EPG.exists():
        raise SystemExit(f"No existe XMLTV: {EPG}")

    request = Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(request, timeout=35) as response:
            page = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"AVISO: no se pudo leer la parrilla oficial de Canal IPe ({exc}); se conserva la guía actual.")
        return

    parser = TextExtractor()
    parser.feed(page)
    lines = [x.strip() for x in "\n".join(parser.parts).splitlines() if x.strip()]
    events = []
    for i, line in enumerate(lines):
        minute = parse_time(line)
        if minute is None:
            continue

        # En la página oficial, cada ficha presenta hora, etiqueta "Ahora",
        # nombre del programa y luego su descripción. Busca el primer texto
        # plausible tras la hora, ignorando etiquetas de interfaz.
        title = None
        for candidate in lines[i + 1:i + 7]:
            normalized = re.sub(r"\s+", " ", candidate).strip()
            low = normalized.casefold()
            if low in SKIP_LINES or low.startswith("disponible en:"):
                continue
            if parse_time(normalized) is not None:
                break
            if len(normalized) > 140:
                continue
            if low.startswith(("programación", "horarios", "canal ipe", "image:", "ver más")):
                continue
            title = normalized
            break
        if not title:
            continue
        # Evita tomar las descripciones largas como si fueran títulos.
        if title.endswith(".") and len(title) > 80:
            continue
        events.append({"minute": minute, "title": title})

    unique = []
    seen = set()
    for event in events:
        key = (event["minute"], event["title"].casefold())
        if key not in seen:
            seen.add(key)
            unique.append(event)
    unique.sort(key=lambda e: e["minute"])

    # Rechaza extracción incompleta o texto de navegación para no publicar
    # una parrilla falsa. Se requiere un mínimo de cinco horarios oficiales.
    if len(unique) < 5:
        print(f"AVISO: solo se detectaron {len(unique)} horarios válidos en {URL}; no se modifica el EPG.")
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
        ET.SubElement(channel, "display-name", {"lang": "es"}).text = CHANNEL_NAME

    # La extracción ya pasó el mínimo de validación. Reemplaza todas las
    # entradas anteriores de este canal para evitar que la programación genérica
    # quede mezclada con la oficial. Los demás canales permanecen intactos.
    for item in list(root.findall("programme")):
        if item.get("channel") == CHANNEL_ID:
            root.remove(item)

    today = datetime.now(LIMA).date()
    for index, event in enumerate(unique):
        start = datetime.combine(today, time(event["minute"] // 60, event["minute"] % 60), tzinfo=LIMA)
        if index + 1 < len(unique):
            next_minute = unique[index + 1]["minute"]
            stop = datetime.combine(today, time(next_minute // 60, next_minute % 60), tzinfo=LIMA)
            if stop <= start:
                stop += timedelta(days=1)
        else:
            stop = start + timedelta(minutes=30)
        if stop <= start:
            continue
        p = ET.SubElement(root, "programme", {
            "start": xml_time(start), "stop": xml_time(stop), "channel": CHANNEL_ID
        })
        ET.SubElement(p, "title", {"lang": "es"}).text = event["title"]
        ET.SubElement(p, "desc", {"lang": "es"}).text = MARKER + " Horario local de Perú (America/Lima)."
        ET.SubElement(p, "category", {"lang": "es"}).text = "Infantil"

    programmes = root.findall("programme")
    programmes.sort(key=lambda p: (p.get("start", ""), p.get("channel", "")))
    first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
    for item in programmes:
        root.remove(item)
    for index, item in enumerate(programmes):
        root.insert(first_programme + index, item)
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Canal IPe: {len(unique)} fichas importadas de la fuente oficial; canal={CHANNEL_ID}; fecha={today}; URL={URL}")

if __name__ == "__main__":
    main()
