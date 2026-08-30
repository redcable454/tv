#!/usr/bin/env python3
import gzip
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
SOURCE_URL = "https://epgshare01.online/epgshare01/epg_ripper_PE1.xml.gz"
LIMA = ZoneInfo("America/Lima")

TARGETS = [
    {
        "id": "liga1.teleclub",
        "name": "Liga1",
        "aliases": ["LIGA 1", "LIGA1", "LIGA 1 TV", "LIGA1 TV"],
    },
    {
        "id": "liga-max.teleclub",
        "name": "Liga Max",
        "aliases": ["LIGA 1 MAX", "LIGA1 MAX", "L1 MAX", "LIGA MAX", "LIGA1MAX"],
    },
    {
        "id": "ovacion-tv.teleclub",
        "name": "Ovación TV",
        "aliases": ["OVACION TV", "OVACIÓN TV", "OVACION", "OVACIÓN"],
    },
]


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def channel_names(ch):
    names = [(x.text or "").strip() for x in ch.findall("display-name") if (x.text or "").strip()]
    if ch.attrib.get("id"):
        names.append(ch.attrib["id"])
    return names


def matches_target(ch, target):
    values = {norm(x) for x in channel_names(ch)}
    wanted = {norm(target["id"]), norm(target["name"]), *(norm(x) for x in target["aliases"])}
    return bool(values & wanted)


def ensure_channel(root, target):
    matches = [ch for ch in root.findall("channel") if matches_target(ch, target)]
    if matches:
        return matches
    ch = ET.Element("channel", {"id": target["id"]})
    ET.SubElement(ch, "display-name", {"lang": "es"}).text = target["name"]
    first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
    root.insert(first_programme, ch)
    return [ch]


def download_source():
    req = Request(SOURCE_URL, headers={"User-Agent": "TeleclubTV-Sports-EPG/1.0"})
    with urlopen(req, timeout=60) as response:
        return ET.fromstring(gzip.decompress(response.read()))


def source_programmes(source_root, target):
    aliases = {norm(target["name"]), *(norm(x) for x in target["aliases"])}
    source_ids = []
    for ch in source_root.findall("channel"):
        names = {norm(x) for x in channel_names(ch)}
        if names & aliases:
            source_ids.append(ch.attrib.get("id", ""))
    source_ids = [x for x in source_ids if x]
    if not source_ids:
        return []
    programmes = []
    for p in source_root.findall("programme"):
        if p.attrib.get("channel") in source_ids and (p.findtext("title") or "").strip():
            programmes.append(p)
    return programmes


def remove_programmes(root, channel_ids):
    ids = set(channel_ids)
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") in ids:
            root.remove(p)


def clone_programmes(root, channel_ids, programmes):
    added = 0
    for cid in channel_ids:
        for p in programmes:
            clone = ET.fromstring(ET.tostring(p, encoding="utf-8"))
            clone.set("channel", cid)
            root.append(clone)
            added += 1
    return added


def add_generic(root, cid, name, days=4):
    existing = any(p.attrib.get("channel") == cid for p in root.findall("programme"))
    if existing:
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
        ET.SubElement(p, "desc", {"lang": "es"}).text = f"Programación deportiva en vivo de {name}."
        ET.SubElement(p, "category", {"lang": "es"}).text = "Deportes"
        root.append(p)
        added += 1
    return added


def main():
    root = ET.parse(EPG).getroot()
    try:
        source = download_source()
    except Exception as exc:
        print(f"WARN: no se pudo descargar la fuente deportiva ({exc}); se usarán datos existentes/fallback.")
        source = None

    total_real = 0
    total_fallback = 0

    for target in TARGETS:
        channels = ensure_channel(root, target)
        ids = [ch.attrib.get("id", target["id"]) for ch in channels]
        programmes = source_programmes(source, target) if source is not None else []

        if programmes:
            remove_programmes(root, ids)
            added = clone_programmes(root, ids, programmes)
            total_real += added
            print(f"SPORT EPG REAL: {target['name']} -> {', '.join(ids)} | programas={added}")
        else:
            added = 0
            for cid in ids:
                added += add_generic(root, cid, target["name"])
            total_fallback += added
            print(f"SPORT EPG FALLBACK: {target['name']} -> {', '.join(ids)} | programas={added}")

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"EPG deportes lista: reales={total_real}, fallback={total_fallback}")


if __name__ == "__main__":
    main()
