import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
LOGOS_DIR = "logos"

# Single primary EPG source
EPG_HEADER_STRING = "https://iptvx.one/epg/epg.xml.gz"

# External playlist endpoints
URL_IPTVRU = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"
URL_LOGANET = "https://loganettv.github.io/playlists/all.m3u"

# GitHub Pages base URL for serving local logos
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "ntvampire/iptv")
REPO_OWNER, REPO_NAME = GITHUB_REPOSITORY.split("/") if "/" in GITHUB_REPOSITORY else ("ntvampire", "iptv")
BASE_PAGES_LOGOS_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/logos"

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
    "лдпр",    
    "инфоканал"
}

# Categories strictly excluded from external sources (lowercase for case-insensitive matching)
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

# Desired output order of categories
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

# Category normalization map
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
    """Search for local logo file in logos/ directory with exact match priority."""
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

    # 1. Exact match priority
    for cand in candidates:
        if not cand:
            continue
        for f in files:
            name_no_ext = os.path.splitext(f)[0].lower()
            if name_no_ext == cand:
                return f"{BASE_PAGES_LOGOS_URL}/{f}"

    # 2. Substring fallback match
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

                # Retrieve logo exclusively from logos/
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

def main():
    # 1. Parse manual channels with local logos from logos/
    manual_channels = load_manual_channels()

    # 2. Parse and merge external sources (Relax/Religion/Local excluded)
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

    # 4. Generate final M3U playlist with primary EPG header
    content = [f'#EXTM3U x-tvg-url="{EPG_HEADER_STRING}"\n']
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

    print(f"\n[+] Playlist generation completed successfully!")
    print(f"    - Manual streams : {len(alive_manual)}")
    print(f"    - External streams: {len(alive_external)}")
    print(f"    - Category order : {' -> '.join(CATEGORY_ORDER)}")

if __name__ == "__main__":
    main()
