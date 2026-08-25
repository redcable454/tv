#!/usr/bin/env python3
import json, unicodedata
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

PANEL='https://teleclubtv-panel.micanalfmradio8.workers.dev/api/admin/channels'
EPG=Path(__file__).with_name('guia_teleclubtv.xml')
LIMA=ZoneInfo('America/Lima')

def norm(s):
    s=unicodedata.normalize('NFD',str(s or '').lower())
    return ''.join(c for c in s if unicodedata.category(c)!='Mn')

def rows():
    req=Request(PANEL,headers={'User-Agent':'TeleclubTV-EPG-Radios/1.1'})
    try:
        with urlopen(req,timeout=30) as r: data=json.loads(r.read().decode())
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f'WARN panel radios: {exc}; usando IDs estables de respaldo')
        return []
    if isinstance(data,dict): return data.get('canales') or data.get('channels') or data.get('data') or []
    return data if isinstance(data,list) else []

def find_id(allrows, aliases, fallback):
    for r in allrows:
        if not isinstance(r,dict): continue
        name=norm(r.get('name') or r.get('nombre'))
        if any(a in name for a in aliases):
            return str(r.get('tvg_id') or r.get('tvgId') or f"custom-{r.get('id')}")
    return fallback

def ensure_channel(root,cid,name):
    for ch in root.findall('channel'):
        names=' '.join((x.text or '') for x in ch.findall('display-name'))
        if ch.attrib.get('id')==cid or norm(name) in norm(names):
            return ch.attrib.get('id')
    ch=ET.Element('channel',{'id':cid})
    ET.SubElement(ch,'display-name',{'lang':'es'}).text=name
    idx=next((i for i,x in enumerate(list(root)) if x.tag=='programme'),len(root))
    root.insert(idx,ch)
    return cid

def replace(root,cid,schedule):
    for p in list(root.findall('programme')):
        if p.attrib.get('channel')==cid: root.remove(p)
    today=datetime.now(LIMA).date(); count=0
    for off in range(7):
        day=today+timedelta(days=off); slots=schedule(day.weekday())
        for start_s,end_s,title in slots:
            sh,sm=map(int,start_s.split(':')); eh,em=map(int,end_s.split(':'))
            start=datetime(day.year,day.month,day.day,sh,sm,tzinfo=LIMA)
            stop=datetime(day.year,day.month,day.day,eh,em,tzinfo=LIMA)
            if stop<=start: stop+=timedelta(days=1)
            p=ET.Element('programme',{'start':start.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S +0000'),'stop':stop.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S +0000'),'channel':cid})
            ET.SubElement(p,'title',{'lang':'es'}).text=title
            root.append(p); count+=1
    return count

def felicidad(w):
    return [('00:00','06:00','La Música De Tu Vida'),('06:00','09:00','Vivamos Felices'),('09:00','12:00','Es la Hora'),('12:00','15:00','Criollazos De Felicidad'),('15:00','19:00','Los Clásicos de Felicidad'),('19:00','00:00','La Música De Tu Vida')]

def oxigeno(w):
    return [('00:00','04:00',"Lo Mejor del Rock N' Pop"),('04:00','06:00','Oxígeno Classics'),('06:00','00:00',"Lo Mejor del Rock N' Pop")]

def corazon(w):
    return [('00:00','14:00','Música continua'),('14:00','21:00','Música continua - Vive +'),('21:00','00:00','Música continua')]

def disney(w):
    return [('00:00','06:00','Radio Disney - Música'),('06:00','22:00','Radio Disney - La radio que te escucha'),('22:00','00:00','Radio Disney - Música')]

def studio(w):
    return [('00:00','06:00','Studio92 Tu mundo, a tu manera'),('06:00','07:00','Las Previas de Wake App'),('07:00','10:00','Wake App'),('10:00','13:00','Backstage'),('13:00','16:00','All In'),('16:00','17:00','Pide Nomás'),('17:00','20:00','Estación 92'),('20:00','00:00','Studio Rewind')]

def planeta(w):
    if w<5:
        return [('00:00','06:00','Música Continuada'),('06:00','07:00','Música Continuada'),('07:00','10:00','Oh my Gachi'),('10:00','13:00','Player'),('13:00','16:00','Sisoi'),('16:00','17:00','Música Continuada'),('17:00','20:00','After'),('20:00','00:00','Música Continuada')]
    if w==5:
        return [('00:00','02:00','Planeta Weekend'),('02:00','13:00','Música Continuada'),('13:00','16:00','Sisoi'),('16:00','00:00','Música Continuada')]
    return [('00:00','02:00','Planeta Weekend'),('02:00','00:00','Música Continuada')]

def main():
    root=ET.parse(EPG).getroot(); allrows=rows()
    specs=[
        ('Radio Felicidad',['felicidad'],'radio-felicidad.teleclub',felicidad),
        ('Radio Oxígeno',['oxigeno'],'radio-oxigeno.teleclub',oxigeno),
        ('Radio Corazón',['corazon'],'radio-corazon.teleclub',corazon),
        ('Radio Disney',['radio disney','disney'],'radio-disney.teleclub',disney),
        ('Studio 92',['studio 92','studio92'],'studio-92.teleclub',studio),
        ('Radio Planeta',['radio planeta','planeta'],'radio-planeta.teleclub',planeta),
    ]
    done=[]
    for label,aliases,fallback,fn in specs:
        cid=find_id(allrows,aliases,fallback)
        cid=ensure_channel(root,cid,label)
        done.append((label,cid,replace(root,cid,fn)))
    ET.indent(root,space='  '); ET.ElementTree(root).write(EPG,encoding='utf-8',xml_declaration=True)
    print('EPG radios:',done)

if __name__=='__main__': main()
