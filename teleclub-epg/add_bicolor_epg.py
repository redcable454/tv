#!/usr/bin/env python3
"""Importa parrillas de TV360 Bitel para Bicolor+, Bicolor+ Premium y L1 MAX."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
CHANNELS = (
    ("https://tv360.bitel.com.pe/tv/bicolor?ch=709", ("bicolor-teleclub",), "Bicolor+", False),
    ("https://tv360.bitel.com.pe/tv/bicolor-premium?ch=704", ("bicolor-premium.teleclub",), "Bicolor+ Premium", False),
    ("https://tv360.bitel.com.pe/tv/l1max?ch=329", ("movistar.lch7216", "604dtv.pe"), "L1 MAX", True),
    ("https://tv360.bitel.com.pe/tv/l1maxmovil?ch=372", ("movistar.lch7217", "603dtv.pe"), "L1", True),
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
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    })
    with urlopen(req, timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
        page_url = response.geturl()

    # Diagnóstico del HTML renderizado: la guía puede venir en los datos SSR de Next.js.
    for marker in ("Programación", "__NEXT_DATA__", "get-live-schedule", "channel_schedule"):
        pos = html.find(marker)
        if pos >= 0:
            print(f"DIAG TV360 HTML {marker}: {html[max(0, pos-500):pos+1800]}")

    # TV360 puede cargar la parrilla desde JavaScript/API. Inspeccionar bundles
    # para descubrir endpoints reales; nunca imprimir query strings ni tokens.
    scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, re.I)
    candidates = set()
    contexts = []
    keywords = ("epg", "schedule", "program", "programacion", "tvguide", "guide", "airing", "broadcast", "eventlist", "channelprogram", "getprogram", "getepg", "starttime", "endtime")
    for script in scripts[:50]:
        script_url = urljoin(page_url, script)
        try:
            req = Request(script_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=25) as response:
                source = response.read(5000000).decode("utf-8", "replace")
            low_source = source.lower()
            for keyword in keywords:
                pos = 0
                hits = 0
                while hits < 4:
                    pos = low_source.find(keyword, pos)
                    if pos < 0:
                        break
                    snippet = re.sub(r"\\s+", " ", source[max(0, pos-180):pos+260])
                    # Evitar imprimir credenciales, tokens o valores de autorización.
                    snippet = re.sub(r"(?i)(token|authorization|password|passwd|secret|cookie)([\\s\"'=:]+)[^,; }]{1,180}", r"\\1\\2[REDACTED]", snippet)
                    contexts.append((keyword, snippet[:420]))
                    hits += 1
                    pos += len(keyword)

            for target in ("get-live-schedule", "get-live-program-box-detail", "get-list-channel", "live-program", "getScheduleCategory", "getChannelCategory", "getQuickChannelList", "baseURL", "axios.create", "img-evg2"):
                pos = 0
                found = 0
                while found < 8:
                    pos = low_source.find(target, pos)
                    if pos < 0:
                        break
                    snippet = re.sub(r"\\s+", " ", source[max(0, pos-700):pos+900])
                    snippet = re.sub(r"(?i)(token|authorization|password|passwd|secret|cookie)([^,; }]{1,180})", r"\\1[REDACTED]", snippet)
                    print(f"DIAG TV360 llamada {target}: {snippet[:1400]}")
                    found += 1
                    pos += len(target)
            for value in re.findall(r"[\"']([^\"']{1,500})[\"']", source):
                low = value.lower()
                if any(k in low for k in ("api", "epg", "program", "schedule", "guide", "graphql", "channel")) and value.startswith(("/", "https://")):
                    candidates.add(urljoin(script_url, value))
        except Exception as exc:
            print(f"DIAG TV360: bundle no inspeccionado ({type(exc).__name__})")
    print(f"DIAG TV360: HTML={len(html)} bytes; scripts={len(scripts)}; endpoints candidatos={len(candidates)}")
    for value in sorted(candidates)[:50]:
        from urllib.parse import urlparse
        parsed = urlparse(value)
        print(f"DIAG TV360 endpoint: {parsed.scheme}://{parsed.netloc}{parsed.path}")
    seen = set()
    for keyword, snippet in contexts:
        if snippet not in seen:
            print(f"DIAG TV360 contexto [{keyword}]: {snippet}")
            seen.add(snippet)
        if len(seen) >= 35:
            break
    # Probar únicamente rutas GET cuyo nombre indique inequívocamente guía/parrilla.
    from urllib.parse import urlparse
    for value in sorted(candidates):
        parsed = urlparse(value)
        route = parsed.path.lower()
        if not any(k in route for k in ("epg", "schedule", "program", "guide", "airing")):
            continue
        try:
            req = Request(value, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"})
            with urlopen(req, timeout=12) as response:
                body = response.read(300000).decode("utf-8", "replace")
                content_type = response.headers.get("Content-Type", "")
                print(f"DIAG TV360 GET {parsed.path}: HTTP={response.status}; type={content_type}; bytes={len(body)}")
                if "json" in content_type.lower() or body.lstrip().startswith(("{", "[")):
                    try:
                        import json
                        data = json.loads(body)
                        keys = list(data.keys())[:25] if isinstance(data, dict) else [type(data).__name__, f"items={len(data)}"]
                        print(f"DIAG TV360 JSON {parsed.path}: keys={keys}")
                    except Exception:
                        pass
        except Exception as exc:
            print(f"DIAG TV360 GET {parsed.path}: {type(exc).__name__}")

    # La API JSON de TV360 se sirve desde img-evg2, no desde el host de la web.
    api_base = "https://img-evg2.tv360.bitel.com.pe"
    api_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://tv360.bitel.com.pe",
        "Referer": page_url,
    }
    for route, params in (
        ("/public/v1/live/get-list-channel", {}),
        ("/public/v1/live/get-more-content", {"id": "channel_schedule_now_v2"}),
    ):
        try:
            from urllib.parse import urlencode
            probe_url = api_base + route + ("?" + urlencode(params) if params else "")
            req = Request(probe_url, headers=api_headers)
            with urlopen(req, timeout=20) as response:
                body = response.read(500000).decode("utf-8", "replace")
                print(f"DIAG TV360 API {route}: HTTP={response.status}; bytes={len(body)}; content-type={response.headers.get('Content-Type', '')}")
                print(f"DIAG TV360 API JSON {route}: {body[:1800]}")
        except Exception as exc:
            status = getattr(exc, "code", "")
            print(f"DIAG TV360 API {route}: {type(exc).__name__}; status={status}")

    parser = TextExtractor()
    parser.feed(html)
    lines = parser.lines
    events = []
    for i, line in enumerate(lines):
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", line)
        if not match:
            continue
        title = next((x for x in lines[i+1:i+5] if x and not re.fullmatch(r"(\d{1,2}):(\d{2})", x)), "")
        if not title or title.lower() in {"programación", "hoy", "bicolor+", "bicolor+ premium", "l1 max", "todas"}:
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
    existing_ids = {ch.attrib.get("id") for ch in root.findall("channel")}
    for url, channel_ids, label, keep_other_days in CHANNELS:
        try:
            events = read_events(url)
        except Exception as exc:
            print(f"AVISO: no se pudo leer {label} desde TV360 ({exc}); se conserva su XML actual.")
            continue
        if len(events) < 2:
            print(f"AVISO: TV360 no expuso una parrilla legible para {label} (eventos={len(events)}); se conserva el XML actual.")
            continue
        target_ids = [cid for cid in channel_ids if cid in existing_ids]
        if not target_ids:
            print(f"AVISO: no existen canales XMLTV para {label} ({', '.join(channel_ids)}); no se agregan programas.")
            continue

        imported_total = 0
        for channel_id in target_ids:
            for programme in list(root.findall("programme")):
                if programme.attrib.get("channel") != channel_id:
                    continue
                if keep_other_days:
                    try:
                        programme_day = datetime.strptime(programme.attrib["start"][:14], "%Y%m%d%H%M%S").date()
                    except (KeyError, ValueError):
                        continue
                    if programme_day != today:
                        continue
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
            imported_total += imported
        print(f"EPG {label} ({', '.join(target_ids)}): {imported_total} programas importados desde TV360 para {today.isoformat()}.")

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
