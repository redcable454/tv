#!/usr/bin/env python3
import re, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
SOURCE = "https://cdn.epg.guru/7dayiptv/Peru.xml"

DROP={"HD","FHD","UHD","4K","TV","CANAL","TELEVISION","CHANNEL","PERU","PE","CABLE"}
def norm(s):
    s=unicodedata.normalize("NFKD",s or "")
    s="".join(c for c in s if not unicodedata.combining(c)).upper().replace("&"," AND ")
    s=re.sub(r"[^A-Z0-9]+"," ",s)
    return " ".join(x for x in s.split() if x not in DROP)

def names(ch):
    return [(x.text or "").strip() for x in ch.findall("display-name") if (x.text or "").strip()]

def generic(p):
    t=(p.findtext("title") or "").strip().lower()
    return t.endswith(" - en vivo")

def main():
    root=ET.parse(EPG).getroot()
    req=Request(SOURCE,headers={"User-Agent":"TeleclubTV-EPG-Updater/1.0","Accept":"application/xml,text/xml,*/*"})
    try:
        with urlopen(req,timeout=90) as r:
            data=r.read()
        src=ET.fromstring(data)
    except Exception as exc:
        print(f"WARN EPG secundaria no disponible: {exc}")
        return

    src_channels=src.findall("channel")
    src_prog={}
    for p in src.findall("programme"):
        cid=p.attrib.get("channel","")
        if cid and (p.findtext("title") or "").strip():
            src_prog.setdefault(cid,[]).append(p)

    exact={c.attrib.get("id",""):c for c in src_channels}
    byname={}
    for c in src_channels:
        sid=c.attrib.get("id","")
        for n in names(c):
            k=norm(n)
            if k: byname.setdefault(k,[]).append((sid,c))

    existing_prog={}
    for p in root.findall("programme"):
        existing_prog.setdefault(p.attrib.get("channel",""),[]).append(p)

    added=matched=0
    for ch in root.findall("channel"):
        cid=ch.attrib.get("id","")
        current=existing_prog.get(cid,[])
        # Solo completar canales sin EPG real; no reemplazar programación existente.
        if current and any(not generic(p) for p in current):
            continue
        sid=""
        if cid in exact and src_prog.get(cid):
            sid=cid
        else:
            for n in names(ch):
                hits=[x for x in byname.get(norm(n),[]) if src_prog.get(x[0])]
                if len(hits)==1:
                    sid=hits[0][0]; break
        if not sid:
            continue
        for p in list(current):
            if generic(p): root.remove(p)
        for p in src_prog[sid]:
            clone=ET.fromstring(ET.tostring(p,encoding="utf-8"))
            clone.set("channel",cid)
            root.append(clone); added+=1
        matched+=1
        print(f"EPG secundaria: {cid} <- {sid} ({len(src_prog[sid])} programas)")

    if matched:
        root.set("secondary-source-info-url",SOURCE)
        ET.indent(root,space="  ")
        ET.ElementTree(root).write(EPG,encoding="utf-8",xml_declaration=True)
    print(f"EPG secundaria: canales completados={matched}, programas agregados={added}")

if __name__=="__main__":
    main()
