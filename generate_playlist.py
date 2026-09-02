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
    
    # Варианты названий для умного поиска в глобальной базе iptv-org
    name_clean = channel_name.lower().strip()
    search_variants = [
        slugify(channel_name).replace("_", ""), # 'traceurban'
        slugify(channel_name),                  # 'trace_urban'
        name_clean.split(" ")[0],               # первое слово, например 'trace' или 'mtv'
    ]
    
    # Если канал содержит слово 'trace', добавим в приоритет базовый логотип Trace
    if "trace" in name_clean:
        search_variants.insert(0, "traceurban")
        
    for variant in search_variants:
        if not variant:
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
            
    # ЧЕТКИЙ ИСПРАВЛЕННЫЙ АДРЕС ЗАГЛУШКИ:
    print(f"⚠️ Логотип для '{channel_name}' не найден в сети. Используем музыкальную заглушку.")
    return "https://githubusercontent.com"


def load_external_iptvru():
    """Скачивает и парсит каналы из проекта IPTVru"""
    channels = {}
    url = "https://githubusercontent.com"
    print("🌐 Загружаем плейлист IPTVru...")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return channels
            
        lines = res.text.splitlines()
        current_inf = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                current_inf = line
            elif line.startswith("http") and current_inf:
                name_match = re.search(r',([^,]+)$', current_inf)
                name = name_match.group(1).strip() if name_match else "Unknown"
                
                group_match = re.search(r'group-title="([^"]+)"', current_inf)
                group = group_match.group(1).strip() if group_match else "Общие"
                
                channels[name] = {"group": group, "url": line}
                current_inf = None
    except Exception as e:
        print(f"Ошибка загрузки IPTVru: {e}")
    return channels

def main():
    final_channels = {}

    # 1. Загружаем из IPTVru
    external = load_external_iptvru()
    final_channels.update(external)

    # 2. Накладываем ваши ручные каналы (у них приоритет)
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

    # 3. Сборка итогового файла
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    
    print(f"\n⚡ Проверяем каналы на работоспособность...")
    for name, data in final_channels.items():
        stream_url = data["url"]
        group = data["group"]
        
        if check_stream(stream_url):
            logo_url = find_and_download_logo(name)
            playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
            playlist_content += f'{stream_url}\n\n'
            print(f"✅ Добавлен: {name}")
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
    print("\n🎉 Готово! Плейлист index.m3u полностью обновлен.")

if __name__ == "__main__":
    main()
