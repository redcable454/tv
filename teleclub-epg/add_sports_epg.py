#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")

TARGETS = {
    "movistar.lch7217": "L1",
    "movistar.lch7216": "L1 MAX",
    "ovacion-tv.teleclub": "Ovación TV",
}

# Programación verificada públicamente para Liga1 / L1 Max.
# Horarios en hora peruana. La duración del bloque de partido se fija en 2h
# para que la guía muestre correctamente el evento actual y el siguiente.
LIGA1_MATCHES = [
    # Fecha 13 - Clausura 2026. Horarios publicados para L1 MAX (hora peruana).
    ("2026-10-23", "13:00", "UTC Cajamarca vs FBC Melgar", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-23", "15:15", "Atlético Grau vs ADT", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-24", "12:45", "Sport Huancayo vs Alianza Atlético", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-24", "15:15", "Cusco FC vs Sporting Cristal", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-24", "20:30", "Universitario vs Juan Pablo II", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-25", "11:00", "Comerciantes Unidos vs Cienciano", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-25", "13:15", "CD Moquegua vs Alianza Lima", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-25", "15:30", "Sport Boys vs FC Cajamarca", "Fecha 13 - Torneo Clausura 2026"),
    ("2026-10-25", "18:00", "Deportivo Garcilaso vs Los Chankas", "Fecha 13 - Torneo Clausura 2026"),
    # Partidos entre semana publicados para el 27-29 de octubre.
    ("2026-10-27", "14:00", "Juan Pablo II vs Sport Huancayo", "Torneo Clausura 2026"),
    ("2026-10-28", "12:00", "ADT vs CD Moquegua", "Torneo Clausura 2026"),
    ("2026-10-28", "14:15", "FC Cajamarca vs UTC Cajamarca", "Torneo Clausura 2026"),
    ("2026-10-28", "16:30", "Alianza Atlético vs Deportivo Garcilaso", "Torneo Clausura 2026"),
    ("2026-10-28", "20:00", "Cienciano vs Atlético Grau", "Torneo Clausura 2026"),
    ("2026-10-29", "14:00", "Los Chankas vs Cusco FC", "Torneo Clausura 2026"),
    ("2026-10-29", "16:30", "Sporting Cristal vs Alianza Lima", "Torneo Clausura 2026"),
    ("2026-10-29", "20:30", "Melgar vs Comerciantes Unidos", "Torneo Clausura 2026"),
]

# Parrilla de Ovación publicada para 2026. La señal TV de Ovación usa esta
# programación deportiva como referencia en la guía de Teleclub TV.
OVACION_WEEKDAY = [
    ("06:00", "09:00", "Impacto Deportivo"),
    ("09:00", "10:00", "Negrini lo Sabe"),
    ("10:00", "12:00", "Full Deporte"),
    ("12:00", "13:00", "De Una"),
    ("13:00", "14:00", "Ovación - Primera Edición"),
    ("15:00", "16:00", "La Sobremesa"),
    ("16:00", "17:00", "La Hora de Lalo"),
    ("17:00", "18:00", "Goles y Salud"),
    ("18:00", "19:00", "Segundo Tiempo"),
    ("19:00", "20:00", "Ovación - Edición Central"),
    ("20:00", "21:00", "Fútbol para Todos"),
]

OVACION_MWF_1400 = "360 en Ovación"
OVACION_TT_1400 = "La Afición Comenta"

OVACION_SATURDAY = [
    ("07:00", "08:00", "Debate Abierto"),
    ("08:00", "10:00", "Zona Deportiva"),
    ("10:00", "12:00", "Previa en Ovación"),
    ("12:00", "19:00", "Transmisiones Deportivas"),
    ("19:00", "20:00", "Ovación - Edición Central"),
    ("20:00", "21:00", "Fusión Latina"),
]

OVACION_SUNDAY = [
    ("08:30", "11:00", "Evolution 360"),
    ("11:00", "13:00", "Previa en Ovación 2"),
    ("13:00", "19:00", "Transmisiones Deportivas 2"),
    ("19:00", "21:00", "Al Cierre con Ovación"),
]


def xml_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def local_dt(day: str, clock: str) -> datetime:
    return datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M").replace(tzinfo=LIMA)


def ensure_channel(root, cid, name):
    ch = next((x for x in root.findall("channel") if x.attrib.get("id") == cid), None)
    if ch is not None:
        dn = ch.find("display-name")
        if dn is None:
            ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
        elif not (dn.text or "").strip():
            dn.text = name
        return
    ch = ET.Element("channel", {"id": cid})
    ET.SubElement(ch, "display-name", {"lang": "es"}).text = name
    first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
    root.insert(first_programme, ch)


def remove_programmes(root, cid, start_day=None, end_day=None):
    # Quita únicamente los eventos deportivos generados por esta rutina,
    # incluidos los eventos de fechas pasadas, y conserva el resto del EPG.
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") != cid:
            continue
        category = " ".join((x.text or "") for x in p.findall("category")).lower()
        desc = (p.findtext("desc") or "").lower()
        if "torneo clausura 2026" in desc or "torneo clausura 2026" in category:
            root.remove(p)


def add_programme(root, cid, start: datetime, stop: datetime, title: str, desc: str, category="Deportes"):
    p = ET.Element("programme", {
        "start": xml_time(start),
        "stop": xml_time(stop),
        "channel": cid,
    })
    ET.SubElement(p, "title", {"lang": "es"}).text = title
    ET.SubElement(p, "desc", {"lang": "es"}).text = desc
    ET.SubElement(p, "category", {"lang": "es"}).text = category
    root.append(p)


def add_liga_programming(root, cid):
    added = 0
    for day, clock, match, round_name in LIGA1_MATCHES:
        start = local_dt(day, clock)
        stop = start + timedelta(hours=2)
        add_programme(
            root,
            cid,
            start,
            stop,
            match,
            f"{round_name}. Partido de Liga1 Te Apuesto 2026. Transmisión deportiva en vivo.",
            "Fútbol",
        )
        added += 1
    return added


def add_ovacion_day(root, day, items):
    added = 0
    for start_clock, stop_clock, title in items:
        start = local_dt(day, start_clock)
        stop = local_dt(day, stop_clock)
        if stop <= start:
            stop += timedelta(days=1)
        add_programme(
            root,
            "ovacion-tv.teleclub",
            start,
            stop,
            title,
            f"Programación deportiva de Ovación. {title}.",
            "Deportes",
        )
        added += 1
    return added


def weekday_items(day: datetime):
    items = list(OVACION_WEEKDAY)
    show_1400 = OVACION_MWF_1400 if day.weekday() in (0, 2, 4) else OVACION_TT_1400
    items.append(("14:00", "15:00", show_1400))
    return sorted(items, key=lambda x: x[0])


def add_ovacion_programming(root):
    added = 0
    start_day = datetime(2026, 8, 29, tzinfo=LIMA).date()
    end_day = datetime(2026, 9, 6, tzinfo=LIMA).date()
    day = start_day
    while day <= end_day:
        iso = day.isoformat()
        weekday = day.weekday()
        if weekday == 5:
            items = OVACION_SATURDAY
        elif weekday == 6:
            items = OVACION_SUNDAY
        else:
            items = weekday_items(datetime.combine(day, datetime.min.time(), tzinfo=LIMA))
        added += add_ovacion_day(root, iso, items)
        day += timedelta(days=1)
    return added


def mirror_channel_programmes(root, source_id, target_id, name):
    """Copia una parrilla XMLTV existente al tvg-id de Teleclub sin inventar programas."""
    ensure_channel(root, target_id, name)
    source_programmes = [
        p for p in root.findall("programme")
        if p.attrib.get("channel") == source_id
    ]
    # No reemplazar una parrilla ya asociada correctamente al ID destino.
    if any(p.attrib.get("channel") == target_id for p in root.findall("programme")):
        return 0
    for p in source_programmes:
        title = (p.findtext("title") or "").strip().lower()
        desc = (p.findtext("desc") or "").strip().lower()
        if title.endswith(" - en vivo") or "bloque informativo de continuidad" in desc:
            continue
        clone = ET.fromstring(ET.tostring(p, encoding="utf-8"))
        clone.set("channel", target_id)
        root.append(clone)
    return sum(1 for p in root.findall("programme") if p.attrib.get("channel") == target_id)


def normalized_channel_name(value):
    value = (value or "").strip().lower()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    value = value.replace("+", " plus ")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in value).split())


def find_schedule_source(root, target_id, accepted_names):
    """Busca la parrilla del mismo XMLTV por nombre, admitiendo sufijos como HD/Perú."""
    accepted = {normalized_channel_name(n) for n in accepted_names}
    wants_max = target_id == "movistar.lch7216"
    channels_with_programmes = {
        p.attrib.get("channel")
        for p in root.findall("programme")
        if (p.findtext("title") or "").strip()
        and not (p.findtext("title") or "").strip().lower().endswith(" - en vivo")
    }
    matches = []
    for ch in root.findall("channel"):
        source_id = ch.attrib.get("id", "")
        if not source_id or source_id == target_id or source_id not in channels_with_programmes:
            continue
        display_names = [x.text or "" for x in ch.findall("display-name")]
        for raw_name in display_names:
            name = normalized_channel_name(raw_name)
            tokens = set(name.split())
            # No confundir L1 con L1 MAX: MAX debe coincidir con el canal destino.
            has_max = "max" in tokens
            if has_max != wants_max:
                continue
            if name in accepted or any(
                name.startswith(alias + " ") or (" " + alias + " ") in (" " + name + " ")
                for alias in accepted
            ):
                matches.append(source_id)
                break
    # Dejar evidencia en Actions cuando el XML no tenga un nombre coincidente.
    if not matches:
        for ch in root.findall("channel"):
            sid = ch.attrib.get("id", "")
            if sid not in channels_with_programmes:
                continue
            names = [x.text or "" for x in ch.findall("display-name")]
            joined = " | ".join(names)
            normalized = normalized_channel_name(joined)
            if any(token in normalized.split() for token in ("l1", "liga", "max", "futbol", "fútbol")):
                print(f"EPG diagnóstico candidato {target_id}: {sid} | {joined}")
    # Si hay más de un canal coincidente, no adivinar cuál es la fuente correcta.
    return matches[0] if len(set(matches)) == 1 else None



def fill_channel_gaps(root, cid, name, days=8):
    """Añade bloques informativos solo donde no exista otro programa, para que la guía no quede vacía."""
    # Elimina los bloques de continuidad anteriores y vuelve a calcular los huecos
    # para que una programación nueva nunca quede tapada por relleno antiguo.
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") == cid and "Bloque informativo de continuidad" in (p.findtext("desc") or ""):
            root.remove(p)
    now = datetime.now(LIMA)
    day_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=LIMA)
    range_start = day_start
    range_end = day_start + timedelta(days=days)

    existing = []
    for p in root.findall("programme"):
        if p.attrib.get("channel") != cid:
            continue
        try:
            start = datetime.strptime(p.attrib["start"], "%Y%m%d%H%M%S %z").astimezone(LIMA)
            stop = datetime.strptime(p.attrib["stop"], "%Y%m%d%H%M%S %z").astimezone(LIMA)
        except (KeyError, ValueError):
            continue
        if stop > range_start and start < range_end and stop > start:
            existing.append((start, stop))

    existing.sort(key=lambda pair: pair[0])
    merged = []
    for start, stop in existing:
        start = max(start, range_start)
        stop = min(stop, range_end)
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))

    gaps = []
    cursor = range_start
    for start, stop in merged:
        while cursor < start:
            gap_stop = min(start, cursor + timedelta(hours=4))
            gaps.append((cursor, gap_stop))
            cursor = gap_stop
        cursor = max(cursor, stop)
    while cursor < range_end:
        gap_stop = min(range_end, cursor + timedelta(hours=4))
        gaps.append((cursor, gap_stop))
        cursor = gap_stop

    for start, stop in gaps:
        add_programme(
            root, cid, start, stop,
            f"Programación de {name}",
            f"Bloque informativo de continuidad de {name}; la guía detallada puede variar según la emisión.",
            "Programación",
        )
    print(f"EPG continuidad {cid}: {len(gaps)} bloques de relleno sin solapar programas existentes")
    return len(gaps)

def main():
    root = ET.parse(EPG).getroot()
    # La URL XMLTV de Teleclub puede contener la parrilla con otro channel ID.
    # Detectar el canal por su nombre dentro del MISMO XML y copiar sus programas
    # al tvg-id usado por la M3U; no descargar ni inventar horarios externos.
    ensure_channel(root, "movistar.lch7217", "L1")
    ensure_channel(root, "movistar.lch7216", "L1 MAX")
    l1_source = find_schedule_source(
        root, "movistar.lch7217",
        {"L1", "L1 HD", "Liga 1", "Liga1", "Liga 1 HD", "Liga1 HD"},
    )
    l1max_source = find_schedule_source(
        root, "movistar.lch7216",
        {"L1 MAX", "L1 MAX HD", "Liga 1 Max", "Liga1 Max", "Liga 1 Max HD", "Liga1 Max HD"},
    )
    if l1_source:
        copied = mirror_channel_programmes(root, l1_source, "movistar.lch7217", "L1")
        print(f"EPG L1: copiados {copied} programas desde ID fuente {l1_source}")
    else:
        print("EPG L1: no se encontró una parrilla fuente con nombre coincidente en el XMLTV")
    if l1max_source:
        copied = mirror_channel_programmes(root, l1max_source, "movistar.lch7216", "L1 MAX")
        print(f"EPG L1 MAX: copiados {copied} programas desde ID fuente {l1max_source}")
    else:
        print("EPG L1 MAX: no se encontró una parrilla fuente con nombre coincidente en el XMLTV")

    # Retirar solamente los bloques genéricos que el propio generador antiguo
    # creó; no sustituir la programación fuente ni espejar un canal sobre otro.
    for p in list(root.findall("programme")):
        cid = p.attrib.get("channel")
        if cid not in ("movistar.lch7217", "movistar.lch7216"):
            continue
        desc = (p.findtext("desc") or "").lower()
        title = (p.findtext("title") or "").lower()
        if (
            "bloque informativo de continuidad" in desc
            or title in ("programación de l1", "programación de l1 max")
        ):
            root.remove(p)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print("EPG L1/L1 MAX: se conserva solo la programación de la fuente, sin parrillas externas ni relleno genérico.")


if __name__ == "__main__":
    main()
