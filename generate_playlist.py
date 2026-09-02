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
    """Преобразует название канала в безопасное имя файла (только латиница и цифры)"""
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

def get_channel_logo(channel_name):
    """
    Ищет логотип канала. Если находит — скачивает в репозиторий и возвращает локальную ссылку.
    Если не находит — возвращает прямую ссылку на красивую внешнюю заглушку (без скачивания).
    """
    os.makedirs(LOGOS_DIR, exist_ok=True)
    
    file_slug = slugify(channel_name)
    if not file_slug:
        file_slug = "channel"
    
    logo_filename = f"{file_slug}.png"
    local_logo_path = os.path.join(LOGOS_DIR, logo_filename)
    
    # Если логотип уже был успешно скачан ранее — выдаем готовую ссылку
    if os.path.exists(local_logo_path):
        return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
    
    name_clean = channel_name.lower().strip()
    search_variants = [file_slug, file_slug.replace("_", "")]
    
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
                print(f"📥 Логотип успешно скачан для: {channel_name}")
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    # ПРЯМАЯ ССЫЛКА-СТРАХОВКА БЕЗ СЛУГЕФИКАЦИИ И СКЛЕИВАНИЯ
    return "https://githubusercontent.com"

def load_external_iptvru():
    """Скачивает и парсит каналы из проекта IPTVru"""
    channels = {}
    url = "https://githubusercontent.com"
    print("🌐 Загружаем стабильный веб-список IPTVru...")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ Не удалось загрузить IPTVru: код {res.status_code}")
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
                
                channels[name] = {"group": group, "url": line, "is_manual": False}
                current_meta = None
                
        print(f"📊 Успешно импортировано из IPTVru: {len(channels)} каналов.")
    except Exception as e:
        print(f"❌ Ошибка обработки внешнего источника: {e}")
    return channels

def main():
    final_channels = {}
    manual_names = set() # Множество для быстрого и безошибочного поиска ручных каналов

    # 1. Загружаем внешнюю базу IPTVru
    external = load_external_iptvru()
    final_channels.update(external)

    # 2. Подгружаем ваши ручные каналы (они в приоритете)
    print(f"📖 Читаем ручной файл {INPUT_FILE}...")
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    name, group, url = parts, parts, parts
                    final_channels[name] = {"group": group, "url": url, "is_manual": True}
                    manual_names.add(name) # Запоминаем имя как ручное
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
        is_manual = data.get("is_manual", False)
        
        # БЕЗОПАСНАЯ ПРОВЕРКА: тестируем только реальные ручные каналы из вашего файла
        if is_manual or name in manual_names:
            if not check_stream(stream_url):
                print(f"❌ Ваш ручной канал [{name}] недоступен. Исключаем.")
                continue
        
        # Получаем ссылку на логотип
        logo_url = get_channel_logo(name)
        
        playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
        playlist_content += f'{stream_url}\n\n'
        added_count += 1
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n🎉 Сборка завершена! Плейлист успешно обновлен.")
    print(f"📊 Добавлено работающих каналов: {added_count} из {total_channels}.")

if __name__ == "__main__":
    main()
