#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

PANEL_URL = "https://teleclubtv-panel.micanalfmradio8.workers.dev/api/admin/channels"
EPG = Path(__file__).with_name("guia_teleclubtv.xml")
LIMA = ZoneInfo("America/Lima")

WEEKDAY = [
    ("00:00", "06:00", "Música Continuada"),
    ("06:00", "10:00", "El Show de Koky Salgado"),
    ("10:00", "12:00", "Momentos Inolvidables con Roxy"),
    ("12:00", "14:00", "Arriba Perú con Kike Vega"),
    ("14:00", "18:00", "Historias de Amor con Allie García"),
    ("18:00", "19:00", "La Hora del Lonchecito con Koky Salgado"),
    ("19:00", "23:00", "Tus Noches Inolvidables"),
    ("23:00", "24:00", "Música Continuada"),
]


def panel_channels():
    req = Request(PANEL_URL, headers={"User-Agent":"TeleclubTV-EPG-Inolvidable/1.0"})
    with urlopen(req, timeout=30) as r:
        data=json.loads(r.read().decode("utf-8"))
    if isinstance(data, dict):
        return data.get("canales") or data.get("channels") or data.get("data") or []
    return data if isinstance(data, list) else []


def norm(s):
    return str(s or "").lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")


def find_radio():
    for r in panel_channels():
        name=r.get("name") or r.get("nombre") or ""
        if "inolvidable" in norm(name):
            cid=str(r.get("tvg_id") or r.get("tvgId") or f"custom-{r.get('id')}").strip()
            return cid, name
    raise RuntimeError("Radio La Inolvidable no fue encontrada en los canales activos del panel")


def dt(day, hhmm):
    if hhmm == "24:00":
        return datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=LIMA)
    h,m=map(int,hhmm.split(":"))
    return datetime(day.year,day.month,day.day,h,m,tzinfo=LIMA)


def main():
    cid,name=find_radio()
    tree=ET.parse(EPG); root=tree.getroot()
    # Quitar programación genérica o anterior de esta radio para evitar duplicados.
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") == cid:
            root.remove(p)
    today=datetime.now(LIMA).date()
    added=0
    for off in range(7):
        day=today+timedelta(days=off)
        # La fuente oficial OIGO confirma esta parrilla de lunes a viernes.
        # Para fin de semana se mantiene una entrada continua hasta disponer de horarios oficiales completos verificables.
        schedule=WEEKDAY if day.weekday() < 5 else [("00:00","24:00",f"{name} - En vivo")]
        for start,stop,title in schedule:
            a=dt(day,start); b=dt(day,stop)
            p=ET.Element("programme", {
                "start":a.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
                "stop":b.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000"),
                "channel":cid,
            })
            ET.SubElement(p,"title",{"lang":"es"}).text=title
            ET.SubElement(p,"desc",{"lang":"es"}).text=f"Programación de {name}. Horario de Perú."
            root.append(p); added+=1
    ET.indent(root, space="  ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Radio La Inolvidable: id={cid}; programas={added}")

if __name__ == "__main__":
    main()
