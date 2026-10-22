#!/usr/bin/env python3
"""Añade al XMLTV la programación oficial publicada por Visión Sur TV."""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")
CHANNEL_ID = "vision-sur-arequipa.teleclub"
CHANNEL_NAME = "Visión Sur TV"
MARKER = "Programación oficial publicada en visionsurtv.pe/programacion/"

# Horarios locales (Perú) publicados en la página oficial del canal.
WEEKDAY = [
    ("00:00", "05:00", "Cine en Casa", "Películas"),
    ("05:00", "06:00", "Un Nuevo Amanecer", "Magazine"),
    ("06:00", "08:00", "Visión Sur Noticias: Primera Edición", "Noticias"),
    ("08:00", "09:00", "Rumbo Electoral", "Política"),
    ("09:00", "10:00", "Series Clásicas", "Series"),
    ("10:00", "12:00", "Ke Buena Mañana", "Magazine"),
    ("12:00", "13:00", "Ke Buen Ritmo", "Magazine"),
    ("13:00", "14:30", "Visión Sur Noticias: Segunda Edición", "Noticias"),
    ("14:30", "17:00", "Cine en Casa", "Películas"),
    ("17:00", "18:00", "Ke Buen Ritmo (Replay)", "Magazine"),
    ("18:00", "20:00", "Ke Buena Mañana (Replay)", "Magazine"),
    ("20:00", "21:30", "Visión Sur Noticias: Edición Central", "Noticias"),
    ("21:30", "22:30", "Rumbo Electoral", "Política"),
    ("22:30", "00:00", "Central Sur Deportes", "Deportes"),
]
SATURDAY = [
    ("00:00", "05:00", "Cine en Casa", "Películas"),
    ("05:00", "07:30", "Un Nuevo Amanecer", "Magazine"),
    ("07:30", "09:00", "Informe Semanal", "Noticias"),
    ("09:00", "10:00", "Series para Niños", "Series"),
    ("10:00", "11:30", "Cine en Casa", "Películas"),
    ("11:30", "13:00", "Informe Semanal (Replay)", "Noticias"),
    ("13:00", "16:00", "Ke Buen Ritmo", "Magazine"),
    ("16:00", "16:30", "Documental", "Documental"),
    ("16:30", "18:00", "Cine en Casa", "Películas"),
    ("18:00", "19:00", "Modo Bicentenario", "Cultura"),
    ("19:00", "20:00", "Cine en Casa", "Películas"),
    ("20:00", "00:00", "Cine en Casa", "Películas"),
]
SUNDAY = [
    ("00:00", "06:00", "Cine en Casa", "Películas"),
    ("06:00", "07:30", "Un Nuevo Amanecer", "Magazine"),
    ("07:30", "09:00", "Informe Semanal (Replay)", "Noticias"),
    ("09:00", "10:00", "Bajo la Lupa", "Noticias"),
    ("10:00", "12:00", "Ke Buena Mañana (Lo mejor de la semana)", "Magazine"),
    ("12:00", "13:00", "Programación Variada", "Cultura"),
    ("13:00", "16:00", "Ke Buen Ritmo", "Magazine"),
    ("16:00", "17:00", "Documental", "Documental"),
    ("17:00", "18:00", "Añoranzas de América", "Musical"),
    ("18:00", "19:00", "Modo Bicentenario", "Cultura"),
    ("19:00", "20:00", "Rumbo Electoral", "Política"),
    ("20:00", "21:00", "Bajo la Lupa (Replay)", "Noticias"),
    ("21:00", "00:00", "Cine en Casa", "Películas"),
]

def xml_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")

def local_datetime(day: date, clock: str, end: bool = False) -> datetime:
    hour, minute = map(int, clock.split(":"))
    result = datetime.combine(day, time(hour, minute), tzinfo=LIMA)
    if end and clock == "00:00":
        result += timedelta(days=1)
    return result

def ensure_channel(root):
    channel = next((c for c in root.findall("channel") if c.attrib.get("id") == CHANNEL_ID), None)
    if channel is None:
        channel = ET.Element("channel", {"id": CHANNEL_ID})
        first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
        root.insert(first_programme, channel)

    # Mantiene el nombre canónico del canal en la guía. El nombre alternativo
    # "Visión Sur TV en vivo" se resuelve en la app por alias, no como otro
    # display-name del canal EPG, para que la guía se identifique como Visión Sur TV.
    for item in list(channel.findall("display-name")):
        if (item.text or "").strip().casefold() == "visión sur tv en vivo":
            channel.remove(item)
    existing_names = {(x.text or "").strip().casefold() for x in channel.findall("display-name")}
    if CHANNEL_NAME.casefold() not in existing_names:
        ET.SubElement(channel, "display-name", {"lang": "es"}).text = CHANNEL_NAME

def main():
    if not EPG.exists():
        raise SystemExit(f"No existe la guía XMLTV: {EPG}")
    tree = ET.parse(EPG)
    root = tree.getroot()
    ensure_channel(root)

    # Reemplaza únicamente los eventos creados por este script; conserva los demás canales.
    for item in list(root.findall("programme")):
        if item.attrib.get("channel") == CHANNEL_ID and MARKER in (item.findtext("desc") or ""):
            root.remove(item)

    today = datetime.now(LIMA).date()
    # Dos semanas de programación, renovadas en cada ejecución automática.
    for offset in range(15):
        day = today + timedelta(days=offset)
        schedule = SATURDAY if day.weekday() == 5 else SUNDAY if day.weekday() == 6 else WEEKDAY
        for start_clock, stop_clock, title, category in schedule:
            start = local_datetime(day, start_clock)
            stop = local_datetime(day, stop_clock, end=True)
            if stop <= start:
                stop += timedelta(days=1)
            programme = ET.SubElement(root, "programme", {
                "start": xml_time(start), "stop": xml_time(stop), "channel": CHANNEL_ID
            })
            ET.SubElement(programme, "title", {"lang": "es"}).text = title
            ET.SubElement(programme, "desc", {"lang": "es"}).text = MARKER + " Horario de Perú (America/Lima). La programación puede cambiar sin previo aviso."
            ET.SubElement(programme, "category", {"lang": "es"}).text = category

    # XMLTV suele ordenarse por hora de inicio para una lectura fiable en reproductores IPTV.
    programmes = root.findall("programme")
    programmes.sort(key=lambda p: (p.attrib.get("start", ""), p.attrib.get("channel", "")))
    first_programme = next((i for i, item in enumerate(list(root)) if item.tag == "programme"), len(root))
    for item in programmes:
        root.remove(item)
    for index, item in enumerate(programmes):
        root.insert(first_programme + index, item)

    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Visión Sur TV: programación añadida para 15 días; canal={CHANNEL_ID}; eventos={sum(1 for p in programmes if p.attrib.get('channel') == CHANNEL_ID)}")

if __name__ == "__main__":
    main()
