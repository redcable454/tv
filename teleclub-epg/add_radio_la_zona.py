#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")
CHANNEL_ID = "custom-28"
CHANNEL_NAME = "Radio La Zona"

# Parrilla vigente consultada en agosto de 2026.
WEEKDAY = [
    ("00:00", "Radio La Zona, Te enciende"),
    ("06:00", "El Flow"),
    ("09:00", "El Break"),
    ("13:00", "Las más encendidas"),
    ("14:00", "Energizona"),
    ("18:00", "De Ida y Vuelta"),
    ("22:00", "Radio La Zona, Te enciende"),
]
FRIDAY = [
    ("00:00", "Radio La Zona, Te enciende"),
    ("06:00", "El Flow"),
    ("09:00", "El Break"),
    ("13:00", "Las más encendidas"),
    ("14:00", "Energizona"),
    ("18:00", "De Ida y Vuelta"),
    ("20:00", "Zona Weekend"),
]
WEEKEND = [
    ("00:00", "Zona Weekend"),
    ("04:00", "Radio La Zona, Te enciende"),
    ("06:00", "El Break"),
    ("13:00", "Radio La Zona, Te enciende"),
    ("15:00", "Clásicos del Reggaetón"),
    ("16:00", "Radio La Zona, Te enciende"),
    ("17:00", "Flow Nacional"),
    ("18:00", "Zona Weekend"),
]
SUNDAY = [
    ("00:00", "Zona Weekend"),
    ("04:00", "Radio La Zona, Te enciende"),
    ("06:00", "El Flow"),
    ("13:00", "Radio La Zona, Te enciende"),
    ("15:00", "Clásicos del Reggaetón"),
    ("16:00", "Radio La Zona, Te enciende"),
    ("17:00", "Flow Nacional"),
    ("18:00", "Zona Weekend"),
]

DESCRIPTIONS = {
    "Radio La Zona, Te enciende": "Lo mejor de la música de Radio La Zona sin interrupciones.",
    "El Flow": "Música, actualidad y entretenimiento para empezar el día con energía.",
    "El Break": "Música, tendencias, entrevistas y entretenimiento.",
    "Las más encendidas": "Las canciones del momento en una hora de música continuada.",
    "Energizona": "Música, juegos y entretenimiento de Radio La Zona.",
    "De Ida y Vuelta": "Música, ocurrencias y entretenimiento para el regreso a casa.",
    "Zona Weekend": "Mezclas y música para encender el fin de semana.",
    "Clásicos del Reggaetón": "Clásicos del reggaetón que marcaron el género urbano.",
    "Flow Nacional": "Artistas nacionales de música urbana, salsa y reparto.",
}


def local_dt(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=LIMA)


def xml_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def schedule_for(day):
    wd = day.weekday()
    if wd <= 3:
        return WEEKDAY
    if wd == 4:
        return FRIDAY
    if wd == 5:
        return WEEKEND
    return SUNDAY


def main():
    tree = ET.parse(EPG)
    root = tree.getroot()

    # Evitar duplicados si el workflow se ejecuta cada 30 minutos.
    for ch in list(root.findall("channel")):
        if ch.attrib.get("id") == CHANNEL_ID:
            root.remove(ch)
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") == CHANNEL_ID:
            root.remove(p)

    ch = ET.Element("channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name", {"lang": "es"}).text = CHANNEL_NAME
    # Los canales deben ir antes de los programme en XMLTV.
    first_programme = next((i for i, e in enumerate(list(root)) if e.tag == "programme"), len(root))
    root.insert(first_programme, ch)

    today = datetime.now(LIMA).date()
    total = 0
    # Incluye ayer para cubrir programas nocturnos y 7 días hacia adelante.
    for offset in range(-1, 8):
        day = today + timedelta(days=offset)
        rows = schedule_for(day)
        for i, (start_s, title) in enumerate(rows):
            start = local_dt(day, start_s)
            if i + 1 < len(rows):
                stop = local_dt(day, rows[i + 1][0])
            else:
                stop = local_dt(day + timedelta(days=1), "00:00")
            p = ET.SubElement(root, "programme", {
                "start": xml_time(start),
                "stop": xml_time(stop),
                "channel": CHANNEL_ID,
            })
            ET.SubElement(p, "title", {"lang": "es"}).text = title
            desc = DESCRIPTIONS.get(title)
            if desc:
                ET.SubElement(p, "desc", {"lang": "es"}).text = desc
            total += 1

    root.set("radio-la-zona-updated-at", datetime.now(timezone.utc).isoformat())
    ET.indent(root, space="  ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Radio La Zona agregada: id={CHANNEL_ID}, programas={total}")


if __name__ == "__main__":
    main()
