import os
import re
import urllib.parse
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"
IPTVRU_SOURCE_URL = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"

# Браузерный User-Agent, чтобы CDN (Cloudfront, Amagi) не отдавали 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    """Проверяет доступность стрима по HEAD или потоковому GET с таймаутом."""
    try:
        # Сначала пробуем HEAD-запрос для экономии трафика
        res = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if res.status_code in (200, 302):
            return True
        # Если HEAD возвращает 405 (Method Not Allowed) или ошибку, пробуем короткий GET
        res = requests.get(url, headers=HEADERS, timeout=5, stream=True)
        if res.status_code == 200:
            return True
    except Exception:
        pass
    return False

def build_iptvx_logo_and_id(channel_name):
    """Возвращает нормализованный tvg-id и прямую ссылку на пикон с сервера iptvX|one."""
    name_clean = channel_name.lower().strip()
    
    # Жесткий маппинг для семейств каналов Trace и XITE
    if "trace urban" in name_clean:
        return "Trace Urban", "https://iptvx.one/picons/Trace_Urban.png"
    elif "trace uk" in name_clean:
        return "Trace UK", "https://iptvx.one/picons/Trace_UK.png"
    elif "trace latina" in name_clean:
        return "Trace Latina", "https://iptvx.one/picons/Trace_Latina.png"
    elif "trace africa" in name_clean:
        return "Trace Africa", "https://iptvx.one/picons/Trace_Africa.png"
    elif "trace muzika" in name_clean:
        return "Trace Muzika", "https://iptvx.one/picons/Trace_Muzika.png"
    elif "trace brazuca" in name_clean:
        return "Trace Brazuca", "https://iptvx.one/picons/Trace_Brazuca.png"
    elif "xite" in name_clean:
        return "Xite Hits", "https://iptvx.one/picons/Xite_Hits.png"
    else:
        file_slug = slugify(channel_name)
        logo_url = f"https://iptvx.one/picons/{file_slug}.png" if file_slug else ""
        return channel_name, logo_url

def load_external_iptvru_stable():
    """Скачивает и парсит плейлист IPTVru."""
    channels = []
    print(f"Загрузка базового плейлиста: {IPTVRU_SOURCE_URL}")
    try:
        res = requests.get(IPTVRU_SOURCE_URL, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"Ошибка загрузки IPTVru, статус: {res.status_code}")
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
    except Exception as e:
        print(f"Исключение при парсинге внешнего плейлиста: {e}")
        
    print(f"Загружено каналов из IPTVru: {len(channels)}")
    return channels

def load_manual_channels():
    """Загружает эксклюзивные каналы из текстового файла с валидацией ссылок."""
    manual_channels = []
    if not os.path.exists(INPUT_FILE):
        print(f"Файл {INPUT_FILE} не найден.")
        return manual_channels

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                name, group, url = parts[0], parts[1], parts[2]
                print(f"Проверка ручного стрима: {name}...")
                if check_stream(url):
                    tvg_id, logo = build_iptvx_logo_and_id(name)
                    manual_channels.append({
                        "name": name,
                        "group": group,
                        "url": url,
                        "logo": logo,
                        "tvg_id": tvg_id
                    })
                    print(f"  [OK] {name}")
                else:
                    print(f"  [FAIL] Канал недоступен и будет пропущен: {name}")
    return manual_channels

def main():
    # 1. Загружаем и проверяем ручные каналы (они будут первыми в списке)
    manual_channels = load_manual_channels()

    # 2. Загружаем каналы из IPTVru
    external_channels = load_external_iptvru_stable()

    # 3. Объединяем: сначала наши эксклюзивные каналы, затем остальной плейлист
    all_channels = manual_channels + external_channels

    if not all_channels:
        print("Внимание: список каналов пуст. Плейлист не будет перезаписан.")
        return

    # 4. Формируем тело m3u
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    for ch in all_channels:
        tvg_id = ch["tvg_id"] or ch["name"]
        logo = ch["logo"]
        group = ch["group"]
        name = ch["name"]
        url = ch["url"]

        playlist_content += (
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}\n'
            f'{url}\n\n'
        )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)

    print(f"Успешно сгенерирован {OUTPUT_FILE}. Всего каналов: {len(all_channels)}")

if __name__ == "__main__":
    main()
