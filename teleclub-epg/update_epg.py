#!/usr/bin/env python3
import gzip
import io
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SOURCE_URL = "https://epgshare01.online/epgshare01/epg_ripper_PE1.xml.gz"
SEED = Path(__file__).with_name("seed_channels.tsv")
OUTPUT = Path(__file__).with_name("guia_teleclubtv.xml")

ALIASES = {
    "latina.teleclub": ["LATINA HD", "LATINA"],
    "america-television.teleclub": ["AMERICA TELEVISION HD", "AMERICA TELEVISION", "AMERICA TV"],
    "panamericana-television.teleclub": ["PANAMERICANA TELEVISION HD", "PANAMERICANA TELEVISION"],
    "atv.teleclub": ["ATV+", "ATV +"],
    "atv.teleclub-2": ["ATV HD", "ATV"],
    "global-tv.teleclub": ["GLOBAL", "RED TV"],
    "cinecanal.teleclub": ["CINECANAL HD", "CINECANAL"],
    "tnt.teleclub": ["TNT HD", "TNT"],
    "willax.teleclub": ["WILLAX"],
    "axn.teleclub": ["AXN HD", "AXN"],
    "history.teleclub": ["HISTORY CHANNEL HD", "HISTORY CHANNEL", "HISTORY"],
    "nick.teleclub": ["NICKELODEON", "NICK HD"],
    "sony.teleclub": ["SONY HD", "SONY"],
    "natgeo.teleclub": ["NAT GEO HD", "NAT GEO"],
}

DROP_WORDS = {
    "CABLE", "PER", "HD", "TV", "CANAL", "TELEVISION", "CHANNEL", "REGIONAL",
    "DTH", "LIVE", "OTT"
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("&AMP;", "&")
    text = re.sub(r"[^A-Z0-9+]+", " ", text)
    words = [w for w in text.split() if w not in DROP_WORDS and not w.isdigit()]
    return " ".join(words).strip()


def similarity(a: str, b: str) -> float:
    aa, bb = set(norm(a).split()), set(norm(b).split())
    if not aa or not bb:
        return 0.0
    common = len(aa & bb)
    return (2.0 * common) / (len(aa) + len(bb))


def load_seed():
    rows = []
    for line in SEED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        cid = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else cid
        icon = parts[2].strip() if len(parts) > 2 else ""
        rows.append((cid, name, icon))
    return rows


def download_source() -> bytes:
    req = Request(SOURCE_URL, headers={"User-Agent": "TeleclubTV-EPG-Updater/1.0"})
    with urlopen(req, timeout=60) as r:
        payload = r.read()
    return gzip.decompress(payload)


def source_channels(root):
    out = []
    for ch in root.findall("channel"):
        sid = ch.attrib.get("id", "")
        names = [(x.text or "").strip() for x in ch.findall("display-name") if (x.text or "").strip()]
        if not names:
            names = [sid]
        out.append((sid, names, ch))
    return out


def choose_source(cid, seed_name, sources):
    candidates = ALIASES.get(cid, []) + [seed_name]
    best = None
    best_score = 0.0
    for sid, names, elem in sources:
        for candidate in candidates:
            for src_name in names + [sid]:
                na, nb = norm(candidate), norm(src_name)
                if not na or not nb:
                    continue
                score = 1.0 if na == nb else similarity(candidate, src_name)
                if na in nb or nb in na:
                    score = max(score, 0.88)
                if score > best_score:
                    best_score = score
                    best = (sid, elem)
    return best if best_score >= 0.67 else None


def main():
    source_xml = download_source()
    src_root = ET.fromstring(source_xml)
    sources = source_channels(src_root)
    programmes_by_id = {}
    for p in src_root.findall("programme"):
        programmes_by_id.setdefault(p.attrib.get("channel", ""), []).append(p)

    out = ET.Element("tv", {
        "source-info-name": "EPGShare01 PE1",
        "source-info-url": SOURCE_URL,
        "generator-info-name": "TeleclubTV Auto EPG",
        "generated-at": datetime.now(timezone.utc).isoformat(),
    })

    matched = 0
    mapping = {}
    for cid, name, icon in load_seed():
        ch = ET.SubElement(out, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
        if icon:
            ET.SubElement(ch, "icon", {"src": icon})

        found = choose_source(cid, name, sources)
        if found:
            sid, _ = found
            mapping[sid] = cid
            matched += 1

    for sid, cid in mapping.items():
        for p in programmes_by_id.get(sid, []):
            clone = ET.fromstring(ET.tostring(p, encoding="utf-8"))
            clone.set("channel", cid)
            out.append(clone)

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    print(f"EPG actualizado: {OUTPUT}")
    print(f"Canales Teleclub mapeados: {matched}/{len(load_seed())}")


if __name__ == "__main__":
    main()
