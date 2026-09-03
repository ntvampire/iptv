import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"
EXTERNAL_SOURCE_URL = "https://loganettv.github.io/playlists/all.m3u"
PICONS_BASE_URL = "https://iptvx.one/picons"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

def check_stream(url):
    """Проверяет доступность стрима: сначала через HEAD, затем потоковый GET."""
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

def resolve_logo_url(logo_field, fallback_name):
    """Преобразует имя файла пикона или полный URL в готовую рабочую ссылку."""
    if not logo_field:
        slug = re.sub(r'[\s-]+', '_', re.sub(r'[^a-zA-Z0-9\s_-]', '', fallback_name).strip())
        return f"{PICONS_BASE_URL}/{slug}.png" if slug else ""
    
    # Если передана полная ссылка (http/https)
    if logo_field.startswith("http://") or logo_field.startswith("https://"):
        return logo_field
    
    # Если передано только имя файла (например, Trace_Urban.png)
    file_name = logo_field if logo_field.endswith(".png") else f"{logo_field}.png"
    return f"{PICONS_BASE_URL}/{file_name}"

def load_manual_channels():
    """Загружает кастомные каналы из input_channels.txt с поддержкой 3, 4 или 5 параметров."""
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
                name = parts[0]
                group = parts[1]
                url = parts[2]
                
                raw_tvg_id = parts[3] if len(parts) >= 4 and parts[3] else name
                raw_logo = parts[4] if len(parts) >= 5 else ""

                print(f"  > Проверка: {name} ... ", end="", flush=True)
                if check_stream(url):
                    logo_url = resolve_logo_url(raw_logo, name)
                    channels.append({
                        "name": name,
                        "group": group,
                        "url": url,
                        "logo": logo_url,
                        "tvg_id": raw_tvg_id
                    })
                    print("OK")
                else:
                    print("НЕ ДОСТУПЕН (пропущен)")
    return channels

def load_external_playlist():
    """Скачивает и парсит внешний базовый плейлист LoganetX."""
    channels = []
    print(f"[*] Загрузка внешнего плейлиста: {EXTERNAL_SOURCE_URL} ...")
    try:
        res = requests.get(EXTERNAL_SOURCE_URL, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"[-] Ошибка загрузки LoganetX: статус {res.status_code}")
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

        print(f"[+] Загружено каналов из LoganetX: {len(channels)}")
    except Exception as e:
        print(f"[-] Исключение при загрузке внешнего плейлиста: {e}")

    return channels

def main():
    manual_channels = load_manual_channels()
    external_channels = load_external_playlist()
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
