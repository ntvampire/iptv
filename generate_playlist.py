import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
LOGOS_DIR = "logos"
EPG_URL = "https://iptvx.one"

# === НАСТРОЙКА ССЫЛКИ (УКАЖИТЕ СВОИ ДАННЫЕ) ===
MY_GITHUB_USERNAME = "ntvampire" 
MY_GITHUB_REPO = "iptv"
# ===============================================

BASE_URL = f"https://{MY_GITHUB_USERNAME}.github.io/{MY_GITHUB_REPO}"

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9а-яё\s-]', '', text)
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    """Оптимизированная и мягкая проверка IPTV потоков"""
    try:
        # Используем обычный GET с ограничением загрузки в 1 секунду, чтобы не злить файрволы
        response = requests.get(url, timeout=3, stream=True)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False

def find_and_download_logo(channel_name):
    os.makedirs(LOGOS_DIR, exist_ok=True)
    logo_filename = f"{slugify(channel_name)}.png"
    local_logo_path = os.path.join(LOGOS_DIR, logo_filename)
    
    if os.path.exists(local_logo_path):
        return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
    
    name_clean = channel_name.lower().strip()
    words = name_clean.split(" ")
    first_word = words[0] if words else ""

    search_variants = [
        slugify(channel_name).replace("_", ""),
        slugify(channel_name),
        first_word
    ]
    
    if "trace" in name_clean:
        search_variants.insert(0, "traceurban")
        
    for variant in search_variants:
        if not variant or len(variant) < 2:
            continue
        test_url = f"https://githubusercontent.com{variant}.png"
        try:
            res = requests.get(test_url, timeout=2)
            if res.status_code == 200:
                with open(local_logo_path, 'wb') as f:
                    f.write(res.content)
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    return "https://githubusercontent.com"

def load_external_iptvru():
    channels = {}
    url = "https://smolnp.github.io/IPTVru//IPTVstable.m3u8"
    print("🌐 Загружаем плейлист IPTVru...")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ Ошибка сети при запросе к IPTVru: {res.status_code}")
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
                
                group = "Общие"
                group_match = re.search(r'group-title="([^"]+)"', current_meta, re.IGNORECASE)
                if group_match:
                    group = group_match.group(1).strip()
                
                channels[name] = {"group": group, "url": line}
                current_meta = None
                
        print(f"📊 Успешно импортировано потенциальных каналов из IPTVru: {len(channels)}")
    except Exception as e:
        print(f"❌ Критическая ошибка парсинга IPTVru: {e}")
    return channels

def main():
    final_channels = {}

    # 1. Загрузка IPTVru
    external = load_external_iptvru()
    final_channels.update(external)

    # 2. Приоритетная загрузка локальных каналов
    print(f"📖 Читаем ваши ручные каналы из {INPUT_FILE}...")
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    name, group, url = parts[0], parts[1], parts[2]
                    final_channels[name] = {"group": group, "url": url}
    else:
        print(f"⚠️ Локальный файл {INPUT_FILE} не найден.")

    # 3. Сборка
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    total_to_check = len(final_channels)
    print(f"\n⚡ Формирование плейлиста (Всего каналов: {total_to_check})...")
    
    added_count = 0
    for name, data in final_channels.items():
        stream_url = data["url"]
        group = data["group"]
        
        # Лайфхак: тщательно проверяем только ваши личные ссылки (из input_channels.txt),
        # а каналы из IPTVru добавляем сразу, чтобы сэкономить время робота.
        is_manual = any(name in line for line in open(INPUT_FILE, "r", encoding="utf-8")) if os.path.exists(INPUT_FILE) else False
        
        if is_manual:
            if not check_stream(stream_url):
                print(f"❌ Ваш ручной канал {name} недоступен. Пропускаем.")
                continue
        
        logo_url = find_and_download_logo(name)
        playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
        playlist_content += f'{stream_url}\n\n'
        added_count += 1
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)

        
    print(f"\n🎉 Плейлист index.m3u успешно сохранен. Добавлено работающих каналов: {added_count} из {total_to_check}.")

if __name__ == "__main__":
    main()
