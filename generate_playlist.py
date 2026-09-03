import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"
IPTVRU_SOURCE_URL = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"

# Заголовки браузера для обхода защиты Amagi, Cloudfront и Trace CDN
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

# Эталонное сопоставление под ваш обновленный список каналов:
# "Название в input_channels.txt": ("tvg-id для EPG", "имя_файла_на_iptvx.png")
IPTVX_MAPPING = {
    "Trace Urban": ("Trace Urban", "Trace_Urban.png"),
    "Trace Urban HD": ("Trace Urban HD", "Trace_Urban_HD.png"),
    "Trace UK": ("Trace UK", "Trace_UK.png"),
    "Trace Latina": ("Trace Latina", "Trace_Latina.png"),
    "Trace Latina 2": ("Trace Latina", "Trace_Latina.png"),       # зеркало/второй поток использует EPG и пикон Trace Latina
    "Trace Urban Australia": ("Trace Urban", "Trace_Urban.png"),
    "Trace Urban France": ("Trace Urban", "Trace_Urban.png"),
    "Trace Africa": ("Trace Africa", "Trace_Africa.png"),
    "Trace Muzika": ("Trace Muzika", "Trace_Muzik.png"),
    "Trace Brazuca": ("Trace Brazuca", "Trace_Brazuca.png"),
    "XITE Hits UK": ("XITE Hits", "XITE_Hits.png"),
}

def check_stream(url):
    """Проверяет доступность стрима: сначала через легкий HEAD, затем GET."""
    try:
        res = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if res.status_code in (200, 302):
            return True
        res = requests.get(url, headers=HEADERS, timeout=5, stream=True)
        if res.status_code == 200:
            return True
    except Exception:
        pass
    return False

def get_iptvx_meta(channel_name):
    """Возвращает корректный tvg-id и URL пикона с iptvX|one."""
    if channel_name in IPTVX_MAPPING:
        tvg_id, picon_file = IPTVX_MAPPING[channel_name]
        return tvg_id, f"https://iptvx.one/picons/{picon_file}"
    
    # Резервный расчет для сторонних названий
    slug = re.sub(r'[\s-]+', '_', re.sub(r'[^a-zA-Z0-9\s_-]', '', channel_name).strip())
    return channel_name, f"https://iptvx.one/picons/{slug}.png" if slug else ""

def load_manual_channels():
    """Загружает кастомные каналы из input_channels.txt с проверкой работоспособности."""
    channels = []
    if not os.path.exists(INPUT_FILE):
        print(f"[-] Файл {INPUT_FILE} не найден.")
        return channels

    print("[*] Обработка ручного списка каналов...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                name, group, url = parts[0], parts[1], parts[2]
                print(f"  > Проверка: {name} ... ", end="", flush=True)
                if check_stream(url):
                    tvg_id, logo_url = get_iptvx_meta(name)
                    channels.append({
                        "name": name,
                        "group": group,
                        "url": url,
                        "logo": logo_url,
                        "tvg_id": tvg_id
                    })
                    print("OK")
                else:
                    print("НЕ ДОСТУПЕН (пропущен)")
    return channels

def load_external_iptvru():
    """Скачивает и парсит внешний базовый плейлист IPTVru."""
    channels = []
    print(f"[*] Загрузка внешнего плейлиста: {IPTVRU_SOURCE_URL} ...")
    try:
        res = requests.get(IPTVRU_SOURCE_URL, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"[-] Ошибка загрузки IPTVru: статус {res.status_code}")
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

                logo_match = re.search(r'tvg-logo="([^"]+)"', current_meta, re.IGNORECASE)
                logo = logo_match.group(1).strip() if logo_match else ""

                group_match = re.search(r'group-title="([^"]+)"', current_meta, re.IGNORECASE)
                group = group_match.group(1).strip() if group_match else "Общие"

                tvg_id_match = re.search(r'tvg-id="([^"]+)"', current_meta, re.IGNORECASE)
                tvg_id = tvg_id_match.group(1).strip() if tvg_id_match else name

                channels.append({
                    "name": name,
                    "group": group,
                    "url": line,
                    "logo": logo,
                    "tvg_id": tvg_id
                })
                current_meta = None

        print(f"[+] Успешно загружено каналов из IPTVru: {len(channels)}")
    except Exception as e:
        print(f"[-] Исключение при загрузке IPTVru: {e}")

    return channels

def main():
    manual_channels = load_manual_channels()
    external_channels = load_external_iptvru()
    all_channels = manual_channels + external_channels

    if not all_channels:
        print("[-] Ошибка: результирующий список каналов пуст. Генерация отменена.")
        return

    content = [f'#EXTM3U x-tvg-url="{EPG_URL}"\n']
    for ch in all_channels:
        tvg_id = ch["tvg_id"] or ch["name"]
        logo = ch["logo"]
        group = ch["group"]
        name = ch["name"]
        url = ch["url"]
        content.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}\n{url}\n')

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("\n".join(content))

    print(f"[+] Готово! Файл {OUTPUT_FILE} обновлен. Всего каналов: {len(all_channels)}")

if __name__ == "__main__":
    main()
