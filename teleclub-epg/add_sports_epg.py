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
    """Publica la misma guía con el tvg-id que usa la lista M3U de Teleclub."""
    ensure_channel(root, target_id, name)
    # Quita el espejo anterior para que las ejecuciones diarias sean idempotentes.
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") == target_id:
            root.remove(p)
    source_programmes = [
        p for p in root.findall("programme")
        if p.attrib.get("channel") == source_id
    ]
    for p in source_programmes:
        clone = ET.fromstring(ET.tostring(p, encoding="utf-8"))
        clone.set("channel", target_id)
        root.append(clone)
    return len(source_programmes)


def main():
    root = ET.parse(EPG).getroot()
    # IDs internos del panel y tvg-id exactos de teleclubtv_con_epg.m3u.
    ensure_channel(root, "movistar.lch7217", "L1")
    ensure_channel(root, "movistar.lch7216", "L1 MAX")
    remove_programmes(root, "movistar.lch7216")

    ligamax_count = add_liga_programming(root, "movistar.lch7216")
    # Publicar la programación de partidos directamente en los IDs solicitados.
    # L1 y L1 MAX comparten aquí los eventos de Liga1 para que ambos muestren guía.
    l1_count = mirror_channel_programmes(root, "movistar.lch7216", "movistar.lch7217", "L1")
    ovacion_count = add_ovacion_programming(root)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(EPG, encoding="utf-8", xml_declaration=True)
    print(
        f"EPG deportiva: L1 MAX={ligamax_count}, "
        f"movistar.lch7217={l1_count}, Ovación TV={ovacion_count}"
    )


if __name__ == "__main__":
    main()
