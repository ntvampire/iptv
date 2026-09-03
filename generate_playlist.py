import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
LOGOS_DIR = "logos"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"

# Источники внешних плейлистов
URL_IPTVRU = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"
URL_LOGANET = "https://loganettv.github.io/playlists/all.m3u"

# Определение GitHub Pages базового URL на основе окружения Actions
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "ntvampire/iptv")
REPO_OWNER, REPO_NAME = GITHUB_REPOSITORY.split("/") if "/" in GITHUB_REPOSITORY else ("ntvampire", "iptv")
BASE_PAGES_LOGOS_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}/logos"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

IGNORED_CHANNEL_NAMES = {
    "loganettv all",
    "telegram - t.me/loganettv_original",
    "telegram - @loganettv_original",
    "loganettv",
    "iptvru"
}

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
    "хобби": "Развлекательные",
    "релакс": "Релакс",
    "медитативные": "Релакс",
    "религия": "Религия",
    "христианские": "Религия"
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

def fetch_tv_logos_index():
    """Загружает полное дерево файлов tv-logo/tv-logos через GitHub API."""
    print("[*] Запрос каталога иконок tv-logo/tv-logos...")
    api_url = "https://api.github.com/repos/tv-logo/tv-logos/git/trees/main?recursive=1"
    try:
        res = requests.get(api_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            tree = res.json().get("tree", [])
            logo_files = [item["path"] for item in tree if item["path"].endswith(".png") and item["path"].startswith("countries/")]
            print(f"[+] Найдено {len(logo_files)} доступных логотипов в базе.")
            return logo_files
    except Exception as e:
        print(f"[-] Ошибка при запросе списка tv-logos: {e}")
    return []

def find_logo_path(channel_name, tvg_id, logo_files):
    """Ищет совпадение по ключевым словам канала в именах файлов tv-logos."""
    candidates = [
        re.sub(r'[^a-z0-9]+', '-', tvg_id.lower()).strip('-'),
        re.sub(r'[^a-z0-9]+', '-', channel_name.lower()).strip('-')
    ]

    # Точный поиск совпадения по префиксу названия
    for cand in candidates:
        # пример cand: trace-urban, trace-latina, xite-hits
        for path in logo_files:
            file_name = path.split("/")[-1].replace(".png", "")
            # Ищем точное вхождение базового slug в имя файла
            if file_name == cand or file_name.startswith(cand + "-") or cand in file_name:
                return path

    return None

def download_and_get_logo_url(channel_name, tvg_id, logo_files):
    """Находит, скачивает иконку в локальную папку logos/ и отдает GitHub Pages ссылку."""
    os.makedirs(LOGOS_DIR, exist_ok=True)

    matched_path = find_logo_path(channel_name, tvg_id, logo_files)
    if not matched_path:
        return ""

    file_name = matched_path.split("/")[-1]
    local_path = os.path.join(LOGOS_DIR, file_name)

    # Скачиваем файл только если его еще нет локально
    if not os.path.exists(local_path):
        raw_url = f"https://raw.githubusercontent.com/tv-logo/tv-logos/main/{matched_path}"
        try:
            r = requests.get(raw_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(r.content)
                print(f"  [+] Скачан логотип: {file_name} для '{channel_name}'")
        except Exception as e:
            print(f"  [-] Не удалось скачать {file_name}: {e}")
            return ""

    return f"{BASE_PAGES_LOGOS_URL}/{file_name}"

def load_manual_channels(logo_files):
    channels = []
    if not os.path.exists(INPUT_FILE):
        return channels

    print("[*] Обработка ручного списка каналов и привязка логотипов...")
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

                # Ищем и скачиваем иконку из tv-logos
                logo_url = download_and_get_logo_url(name, raw_tvg_id, logo_files)

                channels.append({
                    "name": name,
                    "group": group,
                    "url": url,
                    "logo": logo_url,
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

                if is_blacklisted(name):
                    current_meta = None
                    continue

                logo_match = re.search(r'tvg-logo="([^"]*)"', current_meta, re.IGNORECASE)
                logo = logo_match.group(1).strip() if logo_match else ""

                group_match = re.search(r'group-title="([^"]*)"', current_meta, re.IGNORECASE)
                raw_group = group_match.group(1).strip() if group_match else "Общие"
                group = normalize_group(raw_group)

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
    print(f"[*] Старт многопоточной проверки {len(channels)} внешних каналов...")
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
    # 1. Получаем список файлов из репозитория tv-logo
    logo_files = fetch_tv_logos_index()

    # 2. Загружаем и ищем иконки для ручных каналов
    manual_channels = load_manual_channels(logo_files)

    # 3. Скачиваем внешние плейлисты
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

    print(f"\n[+] Генерация завершена успешно!")
    print(f"    - Ручных каналов: {len(alive_manual)}")
    print(f"    - Внешних каналов: {len(alive_external)}")
    print(f"    - Всего в {OUTPUT_FILE}: {len(final_list)}")

if __name__ == "__main__":
    main()
    
