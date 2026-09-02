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
    """Очищает имя канала для создания безопасного имени файла картинок"""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9а-яё\s-]', '', text)
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    """Проверяет, жив ли поток вещания"""
    try:
        response = requests.head(url, timeout=3, allow_redirects=True)
        if response.status_code < 400:
            return True
        response = requests.get(url, timeout=3, stream=True)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False

def find_and_download_logo(channel_name):
    """Ищет логотип в глобальной базе и скачивает его в репозиторий"""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    logo_filename = f"{slugify(channel_name)}.png"
    local_logo_path = os.path.join(LOGOS_DIR, logo_filename)
    
    # Если логотип уже есть в вашей папке, берем его и не качаем заново
    if os.path.exists(local_logo_path):
        return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
    
    print(f"🔍 Ищем логотип для: {channel_name}")
    
    name_clean = channel_name.lower().strip()
    words = name_clean.split(" ")
    first_word = words[0] if words else ""

    search_variants = [
        slugify(channel_name).replace("_", ""), # 'traceurban'
        slugify(channel_name),                  # 'trace_urban'
        first_word                              # 'trace'
    ]
    
    if "trace" in name_clean:
        search_variants.insert(0, "traceurban")
        
    for variant in search_variants:
        if not variant or len(variant) < 2:
            continue
        test_url = f"https://githubusercontent.com{variant}.png"
        try:
            res = requests.get(test_url, timeout=3)
            if res.status_code == 200:
                with open(local_logo_path, 'wb') as f:
                    f.write(res.content)
                print(f"📥 Логотип успешно сохранен в репозиторий: {local_logo_path}")
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    return "https://githubusercontent.com"

def load_external_iptvru():
    """Скачивает и НАДЕЖНО парсит каналы из проекта IPTVru"""
    channels = {}
    url = "https://githubusercontent.com"
    print("🌐 Загружаем плейлист IPTVru...")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ Ошибка загрузки IPTVru: статус {res.status_code}")
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
                # НАДЕЖНЫЙ ПАРСИНГ НАЗВАНИЯ: берем всё, что идет после самой последней запятой в строке
                name = "Unknown Channel"
                if "," in current_meta:
                    name = current_meta.split(",")[-1].strip()
                
                # Извлекаем категорию (группу) канала
                group = "Общие"
                group_match = re.search(r'group-title="([^"]+)"', current_meta, re.IGNORECASE)
                if group_match:
                    group = group_match.group(1).strip()
                
                # Сохраняем во временный словарь
                channels[name] = {"group": group, "url": line}
                current_meta = None
                
        print(f"📊 Успешно распарсено каналов из IPTVru: {len(channels)}")
    except Exception as e:
        print(f"❌ Критическая ошибка при работе с IPTVru: {e}")
    return channels

def main():
    final_channels = {}

    # 1. Сначала загружаем каналы из IPTVru
    external = load_external_iptvru()
    final_channels.update(external)

    # 2. Накладываем ваши ручные каналы из input_channels.txt (у них приоритет)
    print(f"📖 Читаем локальные каналы из {INPUT_FILE}...")
    if os.path.exists(INPUT_FILE):
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
                    # Если канал с таким именем уже был из IPTVru, он перезапишется вашим ручным адресом
                    final_channels[name] = {"group": group, "url": url}
    else:
        print(f"⚠️ Локальный файл {INPUT_FILE} не найден.")

    # 3. Сборка итогового файла с проверкой стримов
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    
    total_to_check = len(final_channels)
    print(f"\n⚡ Начинаем проверку каналов на работоспособность (Всего к проверке: {total_to_check})...")
    
    added_count = 0
    for name, data in final_channels.items():
        stream_url = data["url"]
        group = data["group"]
        
        if check_stream(stream_url):
            logo_url = find_and_download_logo(name)
            playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
            playlist_content += f'{stream_url}\n\n'
            added_count += 1
            print(f"✅ Добавлен рабочий канал: {name} ({group})")
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n🎉 Сборка завершена! Создан файл {OUTPUT_FILE}. Всего рабочих каналов: {added_count} из {total_to_check}.")

if __name__ == "__main__":
    main()
