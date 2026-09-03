import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one/epg/epg.xml.gz"
PICONS_BASE_URL = "https://iptvx.one/picons"

# Источники плейлистов
URL_IPTVRU = "https://smolnp.github.io/IPTVru/IPTVstable.m3u8"
URL_LOGANET = "https://loganettv.github.io/playlists/all.m3u"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
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

def normalize_group(group_title):
    """Сводит разнородные названия групп к единой категории."""
    if not group_title:
        return "Общие"
    clean = group_title.strip().lower()
    return GROUP_NORMALIZATION.get(clean, group_title.strip())

def check_stream(url):
    """Проверяет доступность стрима по HEAD/GET."""
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
    """Формирует URL пикона iptvX|one."""
    if not logo_field:
        slug = re.sub(r'[\s-]+', '_', re.sub(r'[^a-zA-Z0-9\s_-]', '', fallback_name).strip())
        return f"{PICONS_BASE_URL}/{slug}.png" if slug else ""
    if logo_field.startswith("http://") or logo_field.startswith("https://"):
        return logo_field
    file_name = logo_field if logo_field.endswith(".png") else f"{logo_field}.png"
    return f"{PICONS_BASE_URL}/{file_name}"

def load_manual_channels():
    """Загружает эксклюзивные каналы из input_channels.txt."""
    channels = []
    if not os.path.exists(INPUT_FILE):
        print(f"[-] Файл {INPUT_FILE} не найден.")
        return channels

    print("[*] Проверка каналов из input_channels.txt...")
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

                print(f"  > Проверка: {name} ... ", end="", flush=True)
                if check_stream(url):
                    channels.append({
                        "name": name,
                        "group": group,
                        "url": url,
                        "logo": resolve_logo_url(raw_logo, name),
                        "tvg_id": raw_tvg_id
                    })
                    print("OK")
                else:
                    print("НЕ ДОСТУПЕН (пропущен)")
    return channels

def parse_m3u_stream(source_url, source_name):
    """Скачивает и парсит любой m3u/m3u8 плейлист в плоский список словарей."""
    channels = []
    print(f"[*] Загрузка источника {source_name} ({source_url}) ...")
    try:
        res = requests.get(source_url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"[-] Ошибка загрузки {source_name}: код {res.status_code}")
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
                raw_group = group_match.group(1).strip() if group_match else "Общие"
                group = normalize_group(raw_group)

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

        print(f"[+] Из {source_name} загружено: {len(channels)} каналов")
    except Exception as e:
        print(f"[-] Исключение при парсинге {source_name}: {e}")

    return channels

def merge_external_playlists(iptvru_list, loganet_list):
    """
    Объединяет два внешних источника.
    Если названия каналов совпадают — канал из IPTVru вытесняет канал из Loganet.
    """
    merged_dict = {}

    # 1. Сначала вносим каналы Loganet
    for ch in loganet_list:
        key = ch["name"].strip().lower()
        merged_dict[key] = ch

    # 2. Перезаписываем каналами из IPTVru (IPTVru имеет приоритет)
    replaced_count = 0
    for ch in iptvru_list:
        key = ch["name"].strip().lower()
        if key in merged_dict:
            replaced_count += 1
        merged_dict[key] = ch

    print(f"[*] Слияние завершено: {replaced_count} дубликатов из Loganet заменены версиями из IPTVru.")
    return list(merged_dict.values())

def main():
    # 1. Загружаем и валидируем ручные каналы
    manual_channels = load_manual_channels()

    # 2. Скачиваем оба внешних плейлиста
    iptvru_channels = parse_m3u_stream(URL_IPTVRU, "IPTVru")
    loganet_channels = parse_m3u_stream(URL_LOGANET, "LoganetX")

    # 3. Объединяем сторонние плейлисты с приоритетом IPTVru
    external_channels = merge_external_playlists(iptvru_channels, loganet_channels)

    # 4. Исключаем из внешних списков те каналы, которые уже есть в manual (чтобы ваш стрим не продублировался)
    manual_keys = {ch["name"].strip().lower() for ch in manual_channels}
    filtered_external = [ch for ch in external_channels if ch["name"].strip().lower() not in manual_keys]

    # 5. Итоговый список: сначала ваши эксклюзивы, затем общий объединенный каталог
    all_channels = manual_channels + filtered_external

    if not all_channels:
        print("[-] Ошибка: результирующий список пуст. Генерация отменена.")
        return

    # 6. Запись в index.m3u
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

    print(f"[+] Готово! Файл {OUTPUT_FILE} успешно обновлен.")
    print(f"    - Эксклюзивных каналов: {len(manual_channels)}")
    print(f"    - Внешних каналов: {len(filtered_external)}")
    print(f"    - Всего в плейлисте: {len(all_channels)}")

if __name__ == "__main__":
    main()
