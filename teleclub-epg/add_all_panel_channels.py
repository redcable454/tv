#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

PANEL_CHANNELS_URL = "https://teleclubtv-panel.micanalfmradio8.workers.dev/api/admin/channels"
EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")


def fetch_channels():
    req = Request(PANEL_CHANNELS_URL, headers={"User-Agent": "TeleclubTV-EPG-PanelSync/1.1"})
    try:
        with urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"WARN: no se pudo leer /api/admin/channels ({exc}); se conserva la EPG existente y continúan las radios con fallback por nombre.")
        return []
    if isinstance(payload, dict):
        return payload.get("canales") or payload.get("channels") or payload.get("data") or []
    if isinstance(payload, list):
        return payload
    return []


def getv(row, *keys, default=""):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def active(row):
    v = getv(row, "active", "activo", default=1)
    try:
        return int(v) != 0
    except Exception:
        return str(v).strip().lower() not in {"0", "false", "no", "off"}


def ensure_channel(root, cid, name, icon):
    for ch in root.findall("channel"):
        if ch.attrib.get("id") == cid:
            dn = ch.find("display-name")
            if dn is None:
                ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
            if icon and ch.find("icon") is None:
                ET.SubElement(ch, "icon", {"src": icon})
            return False
    ch = ET.Element("channel", {"id": cid})
    ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
    if icon:
        ET.SubElement(ch, "icon", {"src": icon})
    first_programme = next((i for i, x in enumerate(list(root)) if x.tag == "programme"), len(root))
    root.insert(first_programme, ch)
    return True


def has_programmes(root, cid):
    return any(p.attrib.get("channel") == cid for p in root.findall("programme"))


def add_generic_programmes(root, cid, name, category, days=3):
    if has_programmes(root, cid):
        return 0
    today = datetime.now(LIMA).date()
    added = 0
    for offset in range(days):
        day = today + timedelta(days=offset)
        start = datetime.combine(day, datetime.min.time(), tzinfo=LIMA)
        stop = start + timedelta(days=1)
        p = ET.Element("programme", {
            "start": start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
            "stop": stop.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
            "channel": cid,
        })
        ET.SubElement(p, "title", {"lang": "es"}).text = f"{name} - En vivo"
        desc = f"Programación en vivo de {name}."
        if category:
            desc += f" Categoría: {category}."
        ET.SubElement(p, "desc", {"lang": "es"}).text = desc
        root.append(p)
        added += 1
    return added


def main():
    root = ET.parse(EPG).getroot()
    rows = [r for r in fetch_channels() if isinstance(r, dict) and active(r)]
    if not rows:
        print("Panel: endpoint administrativo no disponible públicamente; no se modifica la lista base de canales en este paso.")
        return

    ids = []
    created_channels = 0
    generic_programmes = 0
    radios = 0
    tv = 0

    for r in rows:
        rid = str(getv(r, "tvg_id", "tvgId")).strip()
        if not rid:
            rid = f"custom-{getv(r, 'id')}"
        name = str(getv(r, "name", "nombre", default=f"Canal {rid}")).strip()
        icon = str(getv(r, "logo_url", "logo", default="")).strip()
        category = str(getv(r, "category", "categoría", "categoria", default="")).strip()
        if "radio" in category.lower():
            radios += 1
        else:
            tv += 1
        created_channels += int(ensure_channel(root, rid, name, icon))
        generic_programmes += add_generic_programmes(root, rid, name, category)
        ids.append(rid)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Panel: {len(rows)} activos ({tv} TV / {radios} radios)")
    print(f"Canales XML nuevos: {created_channels}")
    print(f"Programas genéricos agregados: {generic_programmes}")
    print("IDs sincronizados:", ", ".join(ids))


if __name__ == "__main__":
    main()
