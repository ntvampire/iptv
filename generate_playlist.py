import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
EPG_URL = "https://iptvx.one"

def slugify(text):
    """Преобразует название канала в безопасное имя для URL пиконов"""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    """Быстрая проверка доступности потока"""
    try:
        response = requests.get(url, timeout=3, stream=True)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False

def build_iptvx_logo_and_id(channel_name):
    """
    Сопоставляет название вашего канала с точной базой данных iptvX|one.
    Возвращает кортеж: (системный_tvg_id, url_логотипа)
    """
    name_clean = channel_name.lower().strip()
    
    # Реестр точных совпадений для вашей группы каналов на iptvX|one
    if "trace urban" in name_clean:
        tvg_id = "Trace Urban"
        logo_url = "https://iptvx.one"
    elif "trace uk" in name_clean:
        tvg_id = "Trace UK"
        logo_url = "https://iptvx.one"
    elif "trace latina" in name_clean:
        tvg_id = "Trace Latina"
        logo_url = "https://iptvx.one"
    elif "trace africa" in name_clean:
        tvg_id = "Trace Africa"
        logo_url = "https://iptvx.one"
    elif "trace muzika" in name_clean:
        tvg_id = "Trace Muzika"
        logo_url = "https://iptvx.one"
    elif "trace brazuca" in name_clean:
        tvg_id = "Trace Brazuca"
        logo_url = "https://iptvx.one"
    elif "xite" in name_clean:
        tvg_id = "Xite Hits"
        logo_url = "https://iptvx.one"
    else:
        # Автоматический режим для каналов, импортированных из IPTVru
        file_slug = slugify(channel_name)
        tvg_id = channel_name
        logo_url = f"https://iptvx.one{file_slug}.png" if file_slug else ""
        
    return tvg_id, logo_url

def load_external_iptvru_stable():
    """Скачивает и парсит СТАБИЛЬНЫЙ плейлист IPTVru с сохранением оригинальных иконок"""
    channels = {}
    url = "https://smolnp.github.io/IPTVru//IPTVstable.m3u8"
    print("🌐 Загружаем стабильный веб-список IPTVru (IPTVstable.m3u8)...")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ Не удалось загрузить IPTVstable: код {res.status_code}")
            return channels
            
        lines = res.text.splitlines()
        current_meta = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("#EXTINF:"):
                current_meta = line
            elif line.startswith("http") and current_meta:
                name = "Unknown Channel"
                if "," in current_meta:
                    name = current_meta.split(",")[-1].strip()
                
                logo = ""
                logo_match = re.search(r'tvg-logo="([^"]+)"', current_meta, re.IGNORECASE)
                if logo_match:
                    logo = logo_match.group(1).strip()
                
                group = "Общие"
                group_match = re.search(r'group-title="([^"]+)"', current_meta, re.IGNORECASE)
                if group_match:
                    group = group_match.group(1).strip()
                
                tvg_id_match = re.search(r'tvg-id="([^"]+)"', current_meta, re.IGNORECASE)
                tvg_id = tvg_id_match.group(1).strip() if tvg_id_match else name
                
                channels[name] = {"group": group, "url": line, "logo": logo, "tvg_id": tvg_id, "is_manual": False}
                current_meta = None
                
        print(f"📊 Успешно импортировано из IPTVstable: {len(channels)} каналов.")
    except Exception as e:
        print(f"❌ Ошибка обработки стабильного источника: {e}")
    return channels

def main():
    final_channels = {}
    manual_names = set()

    # 1. Загружаем стабильный список IPTVru
    external = load_external_iptvru_stable()
    final_channels.update(external)

    # 2. Подгружаем ваши ручные каналы из input_channels.txt (ИСПРАВЛЕННАЯ РАСПАКОВКА МАССИВА)
    print(f"📖 Читаем ручной файл {INPUT_FILE}...")
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    # Корректное поиндексное извлечение строк вместо ошибочной множественной распаковки
                    name = parts[0]
                    group = parts[1]
                    url = parts[2]
                    
                    final_channels[name] = {"group": group, "url": url, "logo": "", "tvg_id": "", "is_manual": True}
                    manual_names.add(name)
    else:
        print(f"⚠️ Файл {INPUT_FILE} отсутствует.")

    # 3. Сборка финального .m3u файла
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    total_channels = len(final_channels)
    print(f"\n⚡ Начинаем сборку плейлиста. Всего каналов в обработке: {total_channels}")
    
    added_count = 0
    for name, data in final_channels.items():
        stream_url = data["url"]
        group = data["group"]
        logo_url = data["logo"]
        tvg_id = data["tvg_id"]
        is_manual = data.get("is_manual", False)
        
        # Проверяем доступность только для ваших ручных ссылок
        if is_manual or name in manual_names:
            if not check_stream(stream_url):
                print(f"❌ Ваш ручной канал [{name}] недоступен. Исключаем.")
                continue
            # Формируем правильные ID и URL логотипа для базы iptvX|one
            tvg_id, logo_url = build_iptvx_logo_and_id(name)
        
        # Страховочный случай, если логотип пуст
        if not logo_url:
            logo_url = "https://iptvx.one"
            
        # Защита: если для каналов IPTVru не определился tvg-id, используем имя канала
        if not tvg_id:
            tvg_id = name
        
        playlist_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
        playlist_content += f'{stream_url}\n\n'
        added_count += 1
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n🎉 Сборка успешно завершена!")
    print(f"📊 Итог: В плейлист index.m3u сохранено {added_count} каналов.")

if __name__ == "__main__":
    main()
