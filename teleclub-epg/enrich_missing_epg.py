#!/usr/bin/env python3
import re, unicodedata, gzip
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

EPG = Path(__file__).with_name("guia_teleclubtv.xml")
SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_PE1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_CO1.xml.gz",
    "https://cdn.epg.guru/7dayiptv/Peru.xml",
    "https://iptv-epg.org/files/epg-pe.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_SV1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_UY1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    # US1 temporalmente desactivado: su descarga puede superar el timeout del workflow.
    # "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz",
]

DROP={"HD","FHD","UHD","4K","TV","CANAL","TELEVISION","CHANNEL","PERU","PE","CABLE"}
def norm(s):
    s=unicodedata.normalize("NFKD",s or "")
    s="".join(c for c in s if not unicodedata.combining(c)).upper().replace("&"," AND ")
    s=re.sub(r"[^A-Z0-9]+"," ",s)
    return " ".join(x for x in s.split() if x not in DROP)

def names(ch):
    return [(x.text or "").strip() for x in ch.findall("display-name") if (x.text or "").strip()]

def similarity(a,b):
    aa=set(norm(a).split()); bb=set(norm(b).split())
    if not aa or not bb: return 0.0
    return (2.0*len(aa & bb))/(len(aa)+len(bb))

def generic(p):
    t=(p.findtext("title") or "").strip().lower()
    return t.endswith(" - en vivo")

# Alias exactos verificados contra EPGShare PE1. Se usan solo cuando el ID
# de Teleclub difiere del ID XMLTV de la fuente; no afectan el matching general.
SOURCE_ID_ALIASES = {
    "custom-1004": ["CINECANAL.(Cinecanal).pe", "CINECANAL.HD.(Cinecanal.HD).pe", "Cinecanal.co"],
    "custom-1076": ["CNN.ESPAÑOL.(CNNEsp).pe", "CNN.Español.co"],
    "215dtv.cl": ["COMEDY.CENTRAL.HD.(ComedyCentralHD).pe", "Comedy.Central.co"],
    "DISCOVERY.SCIENCE.(Disc.Science).pe": ["Canal.Discovery.Science.(Latinoamérica).sv", "DISCOVERY.SCIENCE.(Disc.Science).pe", "Discovery.Science.co", "Discovery.Science.ar"],
    "custom-1011": ["PARAMOUNT.HD.(Paramount.HD).pe", "PARAMOUNT.(Paramount).pe", "Paramount.Channel.co", "Paramount.ar", "[PARAMNT].Paramount.Network.uy", "PARAMOUNT.NETWORK.HD..uy", "PARAMOUNT.NETWORK..uy"],
    "custom-1058": ["Food.Network.co"],
    "custom-1054": ["HGTV.co"],
    "225dtv.cl": ["PASIONES.co"],
    "custom-1226": ["HBO.2.co"],
    "custom-1227": ["HBO.Family.co", "HBO.FAMILY.ESTE.co"],
    "custom-1229": ["HBO.POP.co"],
    "custom-1230": ["HBO.XTREME.co"],
    "DISCOVERY.TURBO.(Disc.Turbo).pe": ["DISCOVERY.TURBO.(Disc.Turbo).pe"],
    "HISTORY.2.HD.(H2.HD).pe": ["HISTORY.2.HD.(H2.HD).pe", "History.2.co"],
    "HOME.&amp;.HEALTH.HD.(Home&amp;HealthHD).pe": [
        "HOME.&HEALTH.HD.(Home&HealthHD).pe",
        "HOME.&amp;.HEALTH.HD.(Home&amp;HealthHD).pe",
    ],
    "ID.HD.-.INVESTIGATION.DISCOVERY.HD.(Invest.DiscoveryHD).pe": [
        "ID.-.Investigation.Discovery.co",
        "ID.HD.-.INVESTIGATION.DISCOVERY.HD.(Invest.DiscoveryHD).pe",
        "INVESTIGATION.DISCOVERY.HD.(Invest.DiscoveryHD).pe",
    ],
}

def load_source(url):
    req=Request(url,headers={"User-Agent":"TeleclubTV-EPG-Updater/1.1","Accept":"application/xml,text/xml,*/*"})
    with urlopen(req,timeout=90) as r:
        data=r.read()
    if url.lower().endswith(".gz"):
        data=gzip.decompress(data)
    return ET.fromstring(data)

def enrich(root, src, source_url):
    src_channels=src.findall("channel")
    src_prog={}
    for p in src.findall("programme"):
        cid=p.attrib.get("channel","")
        if cid and (p.findtext("title") or "").strip():
            src_prog.setdefault(cid,[]).append(p)

    exact={c.attrib.get("id",""):c for c in src_channels}
    byname={}
    for ch in src_channels:
        sid=ch.attrib.get("id","")
        for n in names(ch):
            k=norm(n)
            if k: byname.setdefault(k,[]).append((sid,ch))

    existing_prog={}
    for p in root.findall("programme"):
        existing_prog.setdefault(p.attrib.get("channel",""),[]).append(p)

    added=matched=0
    for ch in root.findall("channel"):
        cid=ch.attrib.get("id","")
        current=existing_prog.get(cid,[])
        if current and any(not generic(p) for p in current):
            continue
        sid=""
        # 1) ID exacto; 2) alias exacto verificado; 3) nombre seguro.
        if cid in exact and src_prog.get(cid):
            sid=cid
        else:
            for alias in SOURCE_ID_ALIASES.get(cid, []):
                if alias in exact and src_prog.get(alias):
                    sid=alias
                    break
        if not sid:
            for n in names(ch):
                hits=[x for x in byname.get(norm(n),[]) if src_prog.get(x[0])]
                if len(hits)==1:
                    sid=hits[0][0]; break
            if not sid:
                scored=[]
                for srcch in src_channels:
                    ssid=srcch.attrib.get("id","")
                    if not src_prog.get(ssid): continue
                    score=max([similarity(a,b) for a in names(ch) for b in names(srcch)] or [0])
                    if score>=0.92: scored.append((score,ssid))
                scored.sort(reverse=True)
                if scored and (len(scored)==1 or scored[0][0]-scored[1][0]>=0.08):
                    sid=scored[0][1]
        if not sid:
            continue
        for p in list(current):
            if generic(p): root.remove(p)
        for p in src_prog[sid]:
            clone=ET.fromstring(ET.tostring(p,encoding="utf-8"))
            clone.set("channel",cid)
            root.append(clone); added+=1
        matched+=1
        print(f"EPG secundaria {source_url}: {cid} <- {sid} ({len(src_prog[sid])} programas)")
    return matched,added

def main():
    root=ET.parse(EPG).getroot()
    used=[]
    total_matched=total_added=0
    for source in SOURCES:
        try:
            src=load_source(source)
        except Exception as exc:
            print(f"WARN EPG secundaria no disponible {source}: {exc}")
            continue
        matched,added=enrich(root,src,source)
        if matched:
            used.append(source)
            total_matched+=matched; total_added+=added
    if used:
        root.set("secondary-source-info-url"," ".join(used))
        ET.indent(root,space="  ")
        ET.ElementTree(root).write(EPG,encoding="utf-8",xml_declaration=True)
    print(f"EPG secundaria total: canales completados={total_matched}, programas agregados={total_added}")
if __name__=="__main__":
    main()
