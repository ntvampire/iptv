import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"
PICONS_BASE_URL = "https://iptvx.one/picons"

# Источники внешних плейлистов
URL_IPTVRU = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"
URL_LOGANET = "https://loganettv.github.io/playlists/all.m3u"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

# Каналы-пустышки, промо-заглушки и информационные строки для полного игнорирования
IGNORED_CHANNEL_NAMES = {
    "loganettv all",
    "telegram - t.me/loganettv_original",
    "telegram - @loganettv_original",
    "loganettv",
    "iptvru"
}

# Словарь сопоставления групп (приведение к единому стандарту по смыслу)
GROUP_NORMALIZATION = {
    # Кино
    "кино": "Кино и сериалы",
    "фильмы": "Кино и сериалы",
    "сериалы": "Кино и сериалы",
    "cinema": "Кино и сериалы",
    "movies": "Кино и сериалы",
    "кино и сериалы (российские)": "Кино и сериалы",
    # Спорт
    "спорт": "Спорт",
    "спортивные": "Спорт",
    "sports": "Спорт",
    "sport": "Спорт",
    # Музыка
    "музыка": "Музыка",
    "музыкальные": "Музыка",
    "music": "Музыка",
    # Детские
    "детские": "Детские",
    "дети": "Детские",
    "мультфильмы": "Детские",
    "kids": "Детские",
    "детям": "Детские",
    # Новости
    "новости": "Новости",
    "новостные": "Новости",
    "информационные": "Новости",
    "news": "Новости",
    # Познавательные
    "познавательные": "Познавательные",
    "знания": "Познавательные",
    "культура": "Познавательные",
    "образовательные": "Познавательные",
    "наука": "Познавательные",
    "документальные": "Познавательные",
    "discovery": "Познавательные",
    "nature": "Познавательные",
    # Федеральные / Общие
    "общие": "Общие",
    "общественные": "Общие",
    "эфирные": "Общие",
    "федеральные": "Общие",
    "центральные": "Общие",
    # Развлекательные
    "развлекательные": "Развлекательные",
    "развлекательные (местные)": "Развлекательные",
    "развлечение": "Развлекательные",
    "юмор": "Развлекательные",
    "хобби и увлечения": "Развлекательные",
    "хобби": "Развлекательные",
    # Релакс
    "релакс": "Релакс",
    "медитативные": "Релакс",
    # Религия
    "религия": "Религия",
    "христианские": "Религия"
}

def is_blacklisted(channel_name):
    """Проверяет, является ли канал пустышкой или рекламой."""
    clean_name = channel_name.strip().lower()
    if clean_name in IGNORED_CHANNEL_NAMES:
        return True
    for ignored in IGNORED_CHANNEL_NAMES:
        if ignored in clean_name:
            return True
    return False

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
    """Проверяет доступность стрима потока по HEAD и GET."""
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

def resolve_logo_url(logo_field, fallback_name):
    if not logo_field:
        slug = re.sub(r'[\s-]+', '_', re.sub(r'[^a-zA-Z0-9\s_-]', '', fallback_name).strip())
        return f"{PICONS_BASE_URL}/{slug}.png" if slug else ""
    if logo_field.startswith("http://") or logo_field.startswith("https://"):
        return logo_field
    file_name = logo_field if logo_field.endswith(".png") else f"{logo_field}.png"
    return f"{PICONS_BASE_URL}/{file_name}"

def load_manual_channels():
    channels = []
    if not os.path.exists(INPUT_FILE):
        return channels

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
                raw_logo = parts[4] if len(parts) >= 5 else ""

                channels.append({
                    "name": name,
                    "group": group,
                    "url": url,
                    "logo": resolve_logo_url(raw_logo, name),
                    "tvg_id": raw_tvg_id,
                    "is_manual": True
                })
    return channels

def parse_m3u_stream(source_url, source_name):
    channels = []
    print(f"[*] Скачивание: {source_name} ...")
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

                # Фильтрация пустышек и рекламных заглушек
                if is_blacklisted(name):
                    current_meta = None
                    continue

                logo_match = re.search(r'tvg-logo="([^"]+)"', current_meta, re.IGNORECASE)
                logo = logo_match.group(1).strip() if logo_match else ""

                group_match = re.search(r'group-title="([^"]+)"', current_meta, re.IGNORECASE)
                raw_group = group_match.group(1).strip() if group_match else "Общие"
                group = normalize_group(raw_group)

                tvg_id_match = re.search(r'tvg-id="([^"]+)"', current_meta, re.IGNORECASE)
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
        print(f"[-] Ошибка парсинга {source_name}: {e}")
    return channels

def merge_external_playlists(iptvru_list, loganet_list):
    merged = {}
    for ch in loganet_list:
        merged[ch["name"].strip().lower()] = ch
    for ch in iptvru_list:
        merged[ch["name"].strip().lower()] = ch
    return list(merged.values())

def filter_alive_channels(channels, max_workers=30):
    print(f"[*] Старт многопоточной проверки {len(channels)} каналов (потоков: {max_workers})...")
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
                print(f"  > Проверено: {done_count}/{total} | Живых: {len(alive_channels)}")

    return alive_channels

def main():
    manual_channels = load_manual_channels()

    iptvru_channels = parse_m3u_stream(URL_IPTVRU, "IPTVru")
    loganet_channels = parse_m3u_stream(URL_LOGANET, "LoganetX")
    external_channels = merge_external_playlists(iptvru_channels, loganet_channels)

    manual_keys = {ch["name"].strip().lower() for ch in manual_channels}
    filtered_external = [ch for ch in external_channels if ch["name"].strip().lower() not in manual_keys]

    alive_manual = [ch for ch in manual_channels if check_stream(ch)]
    alive_external = filter_alive_channels(filtered_external, max_workers=30)

    final_list = alive_manual + alive_external

    if not final_list:
        print("[-] Ошибка: все потоки недоступны. Файл не перезаписан.")
        return

    content = [f'#EXTM3U x-tvg-url="{EPG_URL}"\n']
    for ch in final_list:
        tvg_id = ch["tvg_id"] or ch["name"]
        logo = ch["logo"]
        group = ch["group"]
        name = ch["name"]
        url = ch["url"]
        content.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}\n{url}\n')

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("\n".join(content))

    print(f"\n[+] Генерация завершена успешно!")
    print(f"    - Ручных активных: {len(alive_manual)} из {len(manual_channels)}")
    print(f"    - Внешних рабочих: {len(alive_external)} из {len(filtered_external)}")
    print(f"    - Итого в {OUTPUT_FILE}: {len(final_list)} каналов")

if __name__ == "__main__":
    main()
    
