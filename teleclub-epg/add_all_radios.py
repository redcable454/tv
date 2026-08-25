#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

PANEL_CHANNELS_URL = "https://teleclubtv-panel.micanalfmradio8.workers.dev/api/admin/channels"
EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")


def fetch_channels():
    req = Request(PANEL_CHANNELS_URL, headers={"User-Agent": "TeleclubTV-EPG-Radios/1.0"})
    with urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("canales") or payload.get("channels") or payload.get("data") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return rows


def getv(row, *keys, default=""):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def is_radio(row):
    cat = str(getv(row, "category", "categoría", "categoria")).strip().lower()
    return cat in {"radios", "radio"} or "radio" in cat


def ensure_channel(root, cid, name, icon):
    for ch in root.findall("channel"):
        if ch.attrib.get("id") == cid:
            return
    ch = ET.Element("channel", {"id": cid})
    ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
    if icon:
        ET.SubElement(ch, "icon", {"src": icon})
    # canales deben ir antes que programme
    first_programme = next((i for i, x in enumerate(list(root)) if x.tag == "programme"), len(root))
    root.insert(first_programme, ch)


def has_programmes(root, cid):
    return any(p.attrib.get("channel") == cid for p in root.findall("programme"))


def add_daily_live_programmes(root, cid, name, days=3):
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
        ET.SubElement(p, "desc", {"lang": "es"}).text = f"Programación en vivo de {name}."
        root.append(p)
        added += 1
    return added


def main():
    root = ET.parse(EPG).getroot()
    rows = fetch_channels()
    radios = [r for r in rows if isinstance(r, dict) and is_radio(r) and int(getv(r, "active", "activo", default=1) or 0) != 0]
    if not radios:
        raise RuntimeError("El panel no devolvió radios activas; se cancela para no publicar una EPG incompleta")

    found_ids = []
    added_programmes = 0
    for r in radios:
        rid = str(getv(r, "tvg_id", "tvgId")).strip()
        if not rid:
            rid = f"custom-{getv(r, 'id')}"
        name = str(getv(r, "name", "nombre", default=f"Radio {rid}")).strip()
        icon = str(getv(r, "logo_url", "logo", default="")).strip()
        ensure_channel(root, rid, name, icon)
        # Si otra etapa (por ejemplo Radio La Zona) ya puso programación real, se conserva.
        added_programmes += add_daily_live_programmes(root, rid, name)
        found_ids.append(rid)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Radios detectadas en panel: {len(radios)}")
    print("IDs:", ", ".join(found_ids))
    print(f"Programas genéricos agregados: {added_programmes}")


if __name__ == "__main__":
    main()
