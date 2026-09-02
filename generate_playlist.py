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
    """Преобразует название канала в безопасное имя файла"""
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

def get_iptvx_logo(channel_name):
    """Ищет логотип канала на серверах iptvX|one, скачивает и сохраняет в репозиторий"""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    file_slug = slugify(channel_name)
    if not file_slug:
        file_slug = "channel"
        
    logo_filename = f"{file_slug}.png"
    local_logo_path = os.path.join(LOGOS_DIR, logo_filename)
    
    # Если логотип уже скачан ранее — отдаем локальную ссылку
    if os.path.exists(local_logo_path):
        return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        
    print(f"🔍 Ищем логотип для ручного канала [{channel_name}] на iptvX|one...")
    
    name_clean = channel_name.lower().strip()
    search_variants = [
        channel_name.replace(" ", "").lower(),  # 'traceurban'
        file_slug,                             # 'trace_urban'
        slugify(channel_name).replace("_", "")  # 'traceurban'
    ]
    
    if "trace" in name_clean:
        search_variants.insert(0, "traceurban")
        search_variants.insert(1, "trace_urban")

    for variant in search_variants:
        if not variant or len(variant) < 2:
            continue
            
        test_url = f"https://iptvx.one{variant}.png"
        try:
            res = requests.get(test_url, timeout=3)
            if res.status_code == 200:
                with open(local_logo_path, 'wb') as f:
                    f.write(res.content)
                print(f"📥 Логотип успешно скачан с iptvX|one: {local_logo_path}")
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    # СТРАХОВОЧНАЯ МУЗЫКАЛЬНАЯ ЗАГЛУШКА НА САЙТЕ iptvX|one
    # Возвращается напрямую в обход любых преобразований текста
    print(f"⚠️ Логотип не найден. Применяется музыкальная заглушка от iptvX|one.")
    return "https://iptvx.one"

def load_external_iptvru_stable():
    """Скачивает и парсит СТАБИЛЬНЫЙ плейлист IPTVru с сохранением оригинальных иконок"""
    channels = {}
    url = "https://githubusercontent.com"
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
                
                channels[name] = {"group": group, "url": line, "logo": logo, "is_manual": False}
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

    # 2. Подгружаем ваши ручные каналы из input_channels.txt
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
                    final_channels[name] = {"group": group, "url": url, "logo": "", "is_manual": True}
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
        is_manual = data.get("is_manual", False)
        
        # Проверяем только ручные ссылки
        if is_manual or name in manual_names:
            if not check_stream(stream_url):
                print(f"❌ Ваш ручной канал [{name}] недоступен. Исключаем.")
                continue
            logo_url = get_iptvx_logo(name)
        
        # Страховочный случай для пустых внешних логотипов
        if not logo_url:
            logo_url = "https://iptvx.one"
        
        playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
        playlist_content += f'{stream_url}\n\n'
        added_count += 1
            
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n🎉 Сборка успешно завершена!")
    print(f"📊 Итог: В плейлист index.m3u сохранено {added_count} каналов.")

if __name__ == "__main__":
    main()
