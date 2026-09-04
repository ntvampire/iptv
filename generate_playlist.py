import os
import re
import gzip
import io
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
OUTPUT_EPG_FILE = "epg.xml.gz"
LOGOS_DIR = "logos"

# External playlist endpoints
URL_IPTVRU = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"
URL_LOGANET = "https://loganettv.github.io/playlists/all.m3u"

# Upstream EPG to filter from
SOURCE_EPG_URL = "https://iptvx.one/epg/epg.xml.gz"

# GitHub Pages base URL configuration
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "ntvampire/iptv")
REPO_OWNER, REPO_NAME = GITHUB_REPOSITORY.split("/") if "/" in GITHUB_REPOSITORY else ("ntvampire", "iptv")
BASE_PAGES_LOGOS_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/logos"
CUSTOM_EPG_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/epg.xml.gz"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

IGNORED_CHANNEL_NAMES = {
    # Original promo & info entries
    "loganettv all",
    "telegram - t.me/loganettv_original",
    "telegram - @loganettv_original",
    "loganettv",
    "iptvru",

    # Teleshopping / promo channels
    "shopping live",
    "ювелирочка",
    "shop & show",
    "leomax",
    "витрина тв",

    # Unwanted generic streams or duplicates
    "тест",
    "сити эдем",
    "deutsche welle",
    "соловьев",
    "maidan",
    "stingray",
    "euronews",
    "лдпр",
    "беларусь",
    "севастополь",
    "крым",
    "екатеринбург",
    "москва",
    "новгород",
    "приднестровье",
    "кубань",
    "пинск тв",
    "юганск",
    "инфоканал"
}

EXCLUDED_EXTERNAL_GROUPS = {
    "релакс",
    "медитативные",
    "relax",
    "религия",
    "христианские",
    "религиозные",
    "православные",
    "religion",
    "местные",
    "региональные"
}

CATEGORY_ORDER = [
    "Общие",
    "Кино и сериалы",
    "Детские",
    "Музыка",
    "Развлекательные",
    "Познавательные",
    "Спорт",
    "Новости"
]
CATEGORY_INDEX_MAP = {cat: idx for idx, cat in enumerate(CATEGORY_ORDER)}

GROUP_NORMALIZATION = {
    "кино": "Кино и сериалы",
    "фильмы": "Кино и сериалы",
    "сериалы": "Кино и сериалы",
    "cinema": "Кино и сериалы",
    "movies": "Кино и сериалы",
    "кино и сериалы (российские)": "Кино и сериалы",
    "спорт": "Спорт",
    "спортивные": "Спорт",
    "sports": "Спорт",
    "sport": "Спорт",
    "музыка": "Музыка",
    "музыкальные": "Музыка",
    "music": "Музыка",
    "детские": "Детские",
    "дети": "Детские",
    "мультфильмы": "Детские",
    "kids": "Детские",
    "детям": "Детские",
    "новости": "Новости",
    "новостные": "Новости",
    "информационные": "Новости",
    "news": "Новости",
    "познавательные": "Познавательные",
    "знания": "Познавательные",
    "культура": "Познавательные",
    "образовательные": "Познавательные",
    "наука": "Познавательные",
    "документальные": "Познавательные",
    "discovery": "Познавательные",
    "nature": "Познавательные",
    "общие": "Общие",
    "общественные": "Общие",
    "эфирные": "Общие",
    "федеральные": "Общие",
    "центральные": "Общие",
    "развлекательные": "Развлекательные",
    "развлекательные (местные)": "Развлекательные",
    "развлечение": "Развлекательные",
    "юмор": "Развлекательные",
    "хобби и увлечения": "Развлекательные",
    "хобби": "Развлекательные"
}

# Force-override channel groups by channel name (lowercase)
CHANNEL_GROUP_OVERRIDES = {
    "trace sport stars": "Спорт",
    "trace sport stars hd": "Спорт"
}

def is_blacklisted(channel_name):
    clean = channel_name.strip().lower()
    if clean in IGNORED_CHANNEL_NAMES:
        return True
    return any(ignored in clean for ignored in IGNORED_CHANNEL_NAMES)

def normalize_group(group_title):
    if not group_title:
        return "Общие"
    clean = group_title.strip().lower()
    if clean in GROUP_NORMALIZATION:
        return GROUP_NORMALIZATION[clean]
    base_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', clean).strip()
    if base_clean in GROUP_NORMALIZATION:
        return GROUP_NORMALIZATION[base_clean]
    return group_title.strip().capitalize()

def check_stream(channel):
    url = channel["url"]
    try:
        res = requests.head(url, headers=HEADERS, timeout=4, allow_redirects=True)
        if res.status_code in (200, 302):
            return channel
        res = requests.get(url, headers=HEADERS, timeout=4, stream=True)
        if res.status_code == 200:
            return channel
    except Exception:
        pass
    return None

def find_local_logo(channel_name, tvg_id):
    if not os.path.exists(LOGOS_DIR):
        return ""

    candidates = [
        tvg_id.lower().strip(),
        re.sub(r'[^a-z0-9]+', '-', channel_name.lower()).strip('-'),
        re.sub(r'[^a-z0-9]+', '_', channel_name.lower()).strip('_'),
        re.sub(r'[^a-z0-9]+', '', channel_name.lower()),
        re.sub(r'[^a-z0-9]+', '-', tvg_id.lower()).strip('-'),
        re.sub(r'[^a-z0-9]+', '_', tvg_id.lower()).strip('_'),
    ]

    files = [f for f in os.listdir(LOGOS_DIR) if f.lower().endswith(".png")]

    for cand in candidates:
        if not cand:
            continue
        for f in files:
            name_no_ext = os.path.splitext(f)[0].lower()
            if name_no_ext == cand:
                return f"{BASE_PAGES_LOGOS_URL}/{f}"

    for cand in candidates:
        if not cand:
            continue
        for f in files:
            name_no_ext = os.path.splitext(f)[0].lower()
            if cand in name_no_ext:
                return f"{BASE_PAGES_LOGOS_URL}/{f}"

    return ""

def load_manual_channels():
    channels = []
    if not os.path.exists(INPUT_FILE):
        return channels

    print("[*] Processing manual channels with local logos from logos/...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                name = parts[0]
                group = normalize_group(parts[1])
                url = parts[2]
                raw_tvg_id = parts[3] if len(parts) >= 4 and parts[3] else name

                logo_url = find_local_logo(name, raw_tvg_id)

                channels.append({
                    "name": name,
                    "group": group,
                    "url": url,
                    "logo": logo_url or "",
                    "tvg_id": raw_tvg_id,
                    "is_manual": True
                })
    return channels

def parse_m3u_stream(source_url, source_name):
    channels = []
    print(f"[*] Fetching external playlist: {source_name} ...")
    try:
        res = requests.get(source_url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return channels

        lines = res.text.splitlines()
        current_meta = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                current_meta = line
            elif (line.startswith("http://") or line.startswith("https://")) and current_meta:
                name = current_meta.split(",")[-1].strip() if "," in current_meta else "Unknown"

                if is_blacklisted(name):
                    current_meta = None
                    continue

                group_match = re.search(r'group-title="([^"]*)"', current_meta, re.IGNORECASE)
                raw_group = group_match.group(1).strip() if group_match else "Общие"

                if raw_group.lower() in EXCLUDED_EXTERNAL_GROUPS:
                    current_meta = None
                    continue

                group = normalize_group(raw_group)
                
# Apply channel-specific group override if defined
clean_name = name.strip().lower()
if clean_name in CHANNEL_GROUP_OVERRIDES:
    group = CHANNEL_GROUP_OVERRIDES[clean_name]
    
                logo_match = re.search(r'tvg-logo="([^"]*)"', current_meta, re.IGNORECASE)
                logo = logo_match.group(1).strip() if logo_match else ""

                tvg_id_match = re.search(r'tvg-id="([^"]*)"', current_meta, re.IGNORECASE)
                tvg_id = tvg_id_match.group(1).strip() if tvg_id_match else name

                channels.append({
                    "name": name,
                    "group": group,
                    "url": line,
                    "logo": logo,
                    "tvg_id": tvg_id,
                    "is_manual": False
                })
                current_meta = None
    except Exception as e:
        print(f"[-] Error parsing {source_name}: {e}")
    return channels

def merge_external_playlists(iptvru_list, loganet_list):
    merged = {}
    for ch in loganet_list:
        merged[ch["name"].strip().lower()] = ch
    for ch in iptvru_list:
        merged[ch["name"].strip().lower()] = ch
    return list(merged.values())

def filter_alive_channels(channels, max_workers=30):
    print(f"[*] Checking {len(channels)} external streams for availability...")
    alive_channels = []
    total = len(channels)
    done_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_channel = {executor.submit(check_stream, ch): ch for ch in channels}
        for future in as_completed(future_to_channel):
            done_count += 1
            res = future.result()
            if res:
                alive_channels.append(res)
            if done_count % 50 == 0 or done_count == total:
                print(f"  > Checked: {done_count}/{total} | Alive: {len(alive_channels)}")

    return alive_channels

def _create_empty_epg():
    """Fallback generator to guarantee epg.xml.gz exists."""
    root = ET.Element("tv")
    tree = ET.ElementTree(root)
    with gzip.open(OUTPUT_EPG_FILE, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)

def generate_custom_epg(channels):
    """Download and filter upstream EPG using stream processing to prevent OOM."""
    target_ids = set()
    for ch in channels:
        if ch.get("tvg_id"):
            target_ids.add(ch["tvg_id"].strip().lower())
        if ch.get("name"):
            target_ids.add(ch["name"].strip().lower())

    temp_gz = "temp_source_epg.xml.gz"
    print(f"[*] Downloading source EPG stream from {SOURCE_EPG_URL}...")
    try:
        with requests.get(SOURCE_EPG_URL, headers=HEADERS, stream=True, timeout=120) as r:
            if r.status_code != 200:
                print(f"[-] Failed to fetch source EPG, HTTP {r.status_code}")
                _create_empty_epg()
                return
            with open(temp_gz, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
        print(f"[+] Downloaded source EPG archive ({os.path.getsize(temp_gz) // 1024} KB)")
    except Exception as e:
        print(f"[-] Error downloading EPG stream: {e}")
        _create_empty_epg()
        return

    print(f"[*] Filtering XMLTV stream for {len(target_ids)} channel identifiers...")
    new_root = ET.Element("tv", {"generator-info-name": "Custom IPTV EPG Generator"})
    matched_channel_ids = set()
    kept_channels = 0
    kept_programmes = 0

    try:
        with gzip.open(temp_gz, "rb") as gz_in:
            context = ET.iterparse(gz_in, events=("end",))
            for _, elem in context:
                if elem.tag == "channel":
                    ch_id = elem.get("id", "").strip()
                    display_name_elem = elem.find("display-name")
                    display_name = display_name_elem.text.strip().lower() if display_name_elem is not None and display_name_elem.text else ""

                    if ch_id.lower() in target_ids or display_name in target_ids:
                        new_root.append(elem)
                        matched_channel_ids.add(ch_id)
                        kept_channels += 1
                    else:
                        elem.clear()

                elif elem.tag == "programme":
                    prog_ch = elem.get("channel", "").strip()
                    if prog_ch in matched_channel_ids or prog_ch.lower() in target_ids:
                        new_root.append(elem)
                        kept_programmes += 1
                    else:
                        elem.clear()

                elif elem.tag not in ("tv",):
                    elem.clear()

        print(f"[+] Retained in custom EPG: {kept_channels} channels and {kept_programmes} programmes.")
        tree = ET.ElementTree(new_root)
        with gzip.open(OUTPUT_EPG_FILE, "wb") as f_out:
            tree.write(f_out, encoding="utf-8", xml_declaration=True)
        print(f"[+] Successfully generated {OUTPUT_EPG_FILE} ({os.path.getsize(OUTPUT_EPG_FILE) // 1024} KB)")

    except Exception as e:
        print(f"[-] Parsing error: {e}")
        _create_empty_epg()
    finally:
        if os.path.exists(temp_gz):
            os.remove(temp_gz)

def main():
    # 1. Parse manual channels with local logos
    manual_channels = load_manual_channels()

    # 2. Parse and merge external sources
    iptvru_channels = parse_m3u_stream(URL_IPTVRU, "IPTVru")
    loganet_channels = parse_m3u_stream(URL_LOGANET, "LoganetX")
    external_channels = merge_external_playlists(iptvru_channels, loganet_channels)

    manual_keys = {ch["name"].strip().lower() for ch in manual_channels}
    filtered_external = [ch for ch in external_channels if ch["name"].strip().lower() not in manual_keys]

    print(f"[*] Verifying manual streams ({len(manual_channels)} channels)...")
    alive_manual = [ch for ch in manual_channels if check_stream(ch)]
    alive_external = filter_alive_channels(filtered_external, max_workers=30)

    final_list = alive_manual + alive_external

    if not final_list:
        print("[-] Error: no playable streams found.")
        return

    # 3. Sort channels strictly by defined category order
    def category_sort_key(channel):
        return CATEGORY_INDEX_MAP.get(channel["group"], len(CATEGORY_ORDER))

    final_list.sort(key=category_sort_key)

    # 4. Generate filtered custom EPG file
    generate_custom_epg(final_list)

    # 5. Generate final M3U playlist with custom GitHub Pages EPG link
    content = [f'#EXTM3U x-tvg-url="{CUSTOM_EPG_URL}"\n']
    for ch in final_list:
        tvg_id = ch["tvg_id"] or ch["name"]
        logo = ch.get("logo", "")
        group = ch["group"]
        name = ch["name"]
        url = ch["url"]

        if logo:
            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}\n{url}\n'
        else:
            extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" group-title="{group}",{name}\n{url}\n'

        content.append(extinf)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("\n".join(content))

    print(f"\n[+] Generation completed successfully!")
    print(f"    - Playlist URL : https://{REPO_OWNER}.github.io/{REPO_NAME}/{OUTPUT_FILE}")
    print(f"    - Custom EPG   : {CUSTOM_EPG_URL}")
    print(f"    - Channels count: {len(final_list)}")

if __name__ == "__main__":
    main()
