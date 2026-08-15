#!/usr/bin/env python3
import gzip
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
    "america-television.teleclub": ["AMERICA TELEVISION HD", "AMERICA TELEVISION", "AMERICA TV", "AMERICA HD", "AMERICA"],
    "panamericana-television.teleclub": ["PANAMERICANA TELEVISION HD", "PANAMERICANA TELEVISION", "PANAMERICANA HD", "PANAMERICANA"],
    "atv.teleclub": ["ATV+", "ATV +", "ATV PLUS"],
    "atv.teleclub-2": ["ATV HD", "ATV"],
    "global-tv.teleclub": ["GLOBAL", "RED TV", "GLOBAL TV"],
    "rpp-tv.teleclub": ["RPP TV", "RPP HD", "RPP"],
    "willas-tv.teleclub": ["WILLAX", "WILLAX TV"],
    "usmp-tv.teleclub": ["USMP TV", "USMP"],
    "la-tele.teleclub": ["LA TELE PERU", "LA TELE"],
    "cine-canal.teleclub": ["CINECANAL HD", "CINECANAL"],
    "sony.teleclub": ["SONY HD", "SONY"],
    "axn.teleclub": ["AXN HD", "AXN"],
    "paramount-chanel.teleclub": ["PARAMOUNT HD", "PARAMOUNT"],
    "a-e.teleclub": ["A&E HD", "A&E", "A AND E"],
    "nick.teleclub": ["NICKELODEON", "NICK HD", "NICK"],
    "disney-chanel.teleclub": ["DISNEY CHANNEL HD", "DISNEY CHANNEL"],
    "discovery-kisd.teleclub": ["DISCOVERY KIDS HD", "DISCOVERY KIDS"],
    "nick-jr.teleclub": ["NICK JR"],
    "disney-jr.teleclub": ["DISNEY JUNIOR", "DISNEY JR"],
    "telemundo.teleclub": ["TELEMUNDO"],
    "espn-1.teleclub": ["ESPN 1 HD", "ESPN 1", "ESPN HD", "ESPN"],
    "espn-2.teleclub": ["ESPN 2 HD", "ESPN 2", "ESPN2 HD", "ESPN2"],
    "espn-3.teleclub": ["ESPN 3 HD", "ESPN 3", "ESPN3 HD", "ESPN3"],
    "animal-planet.teleclub": ["ANIMAL PLANET HD", "ANIMAL PLANET"],
    "discovery-channel.teleclub": ["DISCOVERY CHANNEL", "DISCOVERY HD"],
    "discovery-h-h.teleclub": ["HOME & HEALTH HD", "HOME & HEALTH"],
    "history.teleclub": ["HISTORY CHANNEL HD", "HISTORY CHANNEL", "HISTORY"],
    "national-geographic.teleclub": ["NAT GEO HD", "NAT GEO", "NATIONAL GEOGRAPHIC"],
    "discovery-sciense.teleclub": ["DISCOVERY SCIENCE"],
    "discovery-turbo.teleclub": ["DISCOVERY TURBO"],
    "discovery-theater.teleclub": ["DISCOVERY HD THEATER"],
    "comedi-central.teleclub": ["COMEDY CENTRAL HD", "COMEDY CENTRAL"],
    "lifetime.teleclub": ["LIFETIME"],
    "food-network.teleclub": ["FOOD NETWORK"],
    "enlace.teleclub": ["ENLACE TBN", "ENLACE"],
    "playboy-tv-18.teleclub": ["PLAYBOY HD", "PLAYBOY"],
}

# IDs exactos observados en la fuente PE1. Se priorizan antes de cualquier
# comparación por nombre para recuperar canales válidos sin volver a crear
# falsos positivos como América->Panamericana o A&E->ESPN Extra.
PREFERRED_SOURCE_IDS = {
    "latina.teleclub": "LATINA.HD.(Latina.HD).pe",
    "panamericana-television.teleclub": "PANAMERICANA.TELEVISION.HD.(Panamericana.HD).pe",
    "atv.teleclub-2": "ATV.HD.(ATV.HD).pe",
    "rpp-tv.teleclub": "RPP.HD.(RPP.HD).pe",
    "willas-tv.teleclub": "WILLAX.(Willax).pe",
    "usmp-tv.teleclub": "USMP.TV.(USMP.TV).pe",
    "cine-canal.teleclub": "CINECANAL.HD.(Cinecanal.HD).pe",
    "nick.teleclub": "NICK.HD.(NickHD).pe",
    "disney-chanel.teleclub": "DISNEY.CHANNEL.HD.(DisneyHD).pe",
    "disney-jr.teleclub": "DISNEY.JUNIOR.(DisneyJunior).pe",
    "espn-3.teleclub": "ESPN.3.HD.(ESPN.3.HD).pe",
    "national-geographic.teleclub": "NAT.GEO.HD.(Nat.Geo.HD).pe",
    "comedi-central.teleclub": "COMEDY.CENTRAL.HD.(ComedyCentralHD).pe",
}

DROP_WORDS = {
    "CABLE", "PER", "HD", "FHD", "UHD", "4K", "TV", "CANAL", "TELEVISION", "CHANNEL",
    "REGIONAL", "DTH", "LIVE", "OTT", "LIMA", "PERU"
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("&AMP;", "&")
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9+]+", " ", text)
    words = [w for w in text.split() if w not in DROP_WORDS]
    return " ".join(words).strip()


def token_similarity(a: str, b: str) -> float:
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
    req = Request(SOURCE_URL, headers={"User-Agent": "TeleclubTV-EPG-Updater/1.3"})
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


def programme_is_useful(p):
    return bool((p.findtext("title") or "").strip())


def useful_programmes(programmes_by_id, sid):
    return [p for p in programmes_by_id.get(sid, []) if programme_is_useful(p)]


def choose_source(cid, seed_name, sources, programmes_by_id, used_sources):
    # 0) Fuente exacta ya comprobada en PE1.
    preferred = PREFERRED_SOURCE_IDS.get(cid)
    if preferred and preferred not in used_sources:
        for sid, names, elem in sources:
            if sid == preferred:
                programmes = useful_programmes(programmes_by_id, sid)
                if programmes:
                    return sid, elem, len(programmes), 1.0
                break

    aliases = ALIASES.get(cid, [])
    candidates = aliases + [seed_name]

    # 1) Coincidencias normalizadas exactas.
    for candidate in candidates:
        nc = norm(candidate)
        if not nc:
            continue
        for sid, names, elem in sources:
            if sid in used_sources:
                continue
            programmes = useful_programmes(programmes_by_id, sid)
            if not programmes:
                continue
            if any(norm(v) == nc for v in names):
                return sid, elem, len(programmes), 1.0

    # 2) Fallback conservador por tokens. Los IDs técnicos de la fuente no se
    # comparan aquí porque incluyen sufijos que degradan la similitud.
    best = None
    best_score = 0.0
    for sid, names, elem in sources:
        if sid in used_sources:
            continue
        programmes = useful_programmes(programmes_by_id, sid)
        if not programmes:
            continue
        for candidate in candidates:
            nc = norm(candidate)
            if not nc:
                continue
            c_tokens = set(nc.split())
            for src_name in names:
                ns = norm(src_name)
                if not ns:
                    continue
                s_tokens = set(ns.split())
                if min(len(c_tokens), len(s_tokens)) <= 1:
                    continue
                score = token_similarity(candidate, src_name)
                c_nums = {t for t in c_tokens if t.isdigit()}
                s_nums = {t for t in s_tokens if t.isdigit()}
                if c_nums and c_nums != s_nums:
                    continue
                if score > best_score:
                    best_score = score
                    best = (sid, elem, len(programmes), score)

    return best if best_score >= 0.90 else None


def main():
    source_xml = download_source()
    src_root = ET.fromstring(source_xml)
    sources = source_channels(src_root)
    programmes_by_id = {}
    for p in src_root.findall("programme"):
        sid = p.attrib.get("channel", "")
        if sid:
            programmes_by_id.setdefault(sid, []).append(p)

    out = ET.Element("tv", {
        "source-info-name": "EPGShare01 PE1",
        "source-info-url": SOURCE_URL,
        "generator-info-name": "TeleclubTV Auto EPG",
        "generated-at": datetime.now(timezone.utc).isoformat(),
    })

    matched = 0
    mapping = {}
    used_sources = set()
    seed_rows = load_seed()
    unmatched = []

    for cid, name, icon in seed_rows:
        found = choose_source(cid, name, sources, programmes_by_id, used_sources)
        if not found:
            unmatched.append((cid, name))
            continue

        sid, _, programme_count, score = found
        mapping[sid] = cid
        used_sources.add(sid)
        ch = ET.SubElement(out, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
        if icon:
            ET.SubElement(ch, "icon", {"src": icon})
        matched += 1
        print(f"MAP {cid} <- {sid} | programas={programme_count} | score={score:.2f}")

    programme_total = 0
    for sid, cid in mapping.items():
        for p in useful_programmes(programmes_by_id, sid):
            clone = ET.fromstring(ET.tostring(p, encoding="utf-8"))
            clone.set("channel", cid)
            out.append(clone)
            programme_total += 1

    if matched == 0 or programme_total == 0:
        raise RuntimeError("La fuente no entregó canales con programación útil; no se reemplaza la EPG actual")

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    print(f"EPG actualizado: {OUTPUT}")
    print(f"Canales con programación real: {matched}/{len(seed_rows)}")
    print(f"Programas publicados: {programme_total}")
    if unmatched:
        print("Canales sin programación disponible en la fuente:")
        for cid, name in unmatched:
            print(f"  - {cid} | {name}")


if __name__ == "__main__":
    main()
