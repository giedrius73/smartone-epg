#!/usr/bin/env python3
import gzip
import io
import re
import requests
from datetime import datetime, timedelta
from difflib import SequenceMatcher

M3U_URL = "http://8b7a69015e35.goodstreem.org/playlists/uplist/067f288518a068f4f0f8f3152e06405f/playlist.m3u8"
EPG_URL = "http://epg.one/epg2.xml.gz"

OUTPUT_M3U = "playlist_su_epg.m3u8"
OUTPUT_EPG = "epg_su_filtru.xml.gz"

MIN_SIMILARITY = 0.82  # konservatyvus B1 slenkstis

def download_text(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text

def download_gzip_xml(url):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as f:
        return f.read().decode("utf-8", errors="ignore")

def parse_m3u_channels(m3u_text):
    channels = []
    lines = m3u_text.splitlines()
    current_name = None

    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            if "," in line:
                current_name = line.split(",", 1)[1].strip()
            else:
                current_name = None
        elif line and not line.startswith("#") and current_name:
            channels.append((current_name, line))
            current_name = None

    return channels

def parse_epg_channels(epg_xml):
    epg_channels = {}
    channel_blocks = re.findall(r"<channel id=\"(.*?)\">(.*?)</channel>", epg_xml, re.DOTALL)
    for cid, inner in channel_blocks:
        names = re.findall(r"<display-name[^>]*>(.*?)</display-name>", inner)
        clean_names = [re.sub(r"\s+", " ", n).strip() for n in names]
        if clean_names:
            epg_channels[cid] = clean_names
    return epg_channels

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_best_match(channel_name, epg_channels):
    best_id = None
    best_score = 0.0

    for cid, names in epg_channels.items():
        for n in names:
            score = similarity(channel_name, n)
            if score > best_score:
                best_score = score
                best_id = cid

    if best_score >= MIN_SIMILARITY:
        return best_id, best_score
    return None, best_score

def build_new_m3u(channels, mapping):
    out_lines = ['#EXTM3U url-tvg="epg_su_filtru.xml.gz"']
    for name, url in channels:
        cid = mapping.get(name)
        if cid:
            out_lines.append(f'#EXTINF:-1 tvg-id="{cid}",{name}')
        else:
            out_lines.append(f'#EXTINF:-1,{name}')
        out_lines.append(url)
    return "\n".join(out_lines) + "\n"

def build_filtered_epg(epg_xml, used_ids):
    header_match = re.search(r"^(.*?<tv[^>]*>)", epg_xml, re.DOTALL)
    if header_match:
        header = header_match.group(1)
    else:
        header = '<?xml version="1.0" encoding="utf-8"?><tv>'

    footer = "</tv>"

    channels = re.findall(r"<channel id=\"(.*?)\">(.*?)</channel>", epg_xml, re.DOTALL)
    programmes = re.findall(r"<programme(.*?)</programme>", epg_xml, re.DOTALL)

    out = [header]

    for cid, inner in channels:
        if cid in used_ids:
            out.append(f'<channel id="{cid}">{inner}</channel>')

    for block in programmes:
        ch_match = re.search(r'channel="(.*?)"', block)
        if ch_match and ch_match.group(1) in used_ids:
            out.append(f"<programme{block}</programme>")

    out.append(footer)
    return "\n".join(out)

def main():
    print("Parsisiunčiu M3U...")
    m3u_text = download_text(M3U_URL)

    print("Parsisiunčiu EPG...")
    epg_xml = download_gzip_xml(EPG_URL)

    print("Analizuoju M3U kanalus...")
    channels = parse_m3u_channels(m3u_text)
    print(f"Rasta kanalų M3U: {len(channels)}")

    print("Analizuoju EPG kanalus...")
    epg_channels = parse_epg_channels(epg_xml)
    print(f"Rasta kanalų EPG: {len(epg_channels)}")

    mapping = {}
    used_ids = set()

    print("Atlieku konservatyvų fuzzy matching (B1)...")
    for name, url in channels:
        cid, score = find_best_match(name, epg_channels)
        if cid:
            mapping[name] = cid
            used_ids.add(cid)
            print(f"[OK] '{name}' → id={cid} (score={score:.3f})")
        else:
            print(f"[SKIP] '{name}' (max score={score:.3f})")

    print("Generuoju naują M3U su tvg-id...")
    new_m3u = build_new_m3u(channels, mapping)
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write(new_m3u)

    print("Generuoju filtruotą EPG...")
    filtered_epg = build_filtered_epg(epg_xml, used_ids)
    with gzip.open(OUTPUT_EPG, "wb") as f:
        f.write(filtered_epg.encode("utf-8"))

    print("BAIGTA.")
    print("Sukurti failai:")
    print(" -", OUTPUT_M3U)
    print(" -", OUTPUT_EPG)

if __name__ == "__main__":
    main()
