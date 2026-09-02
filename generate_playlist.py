import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
LOGOS_DIR = "logos"
EPG_URL = "https://iptvx.one"  # Отличный EPG источник для СНГ/РФ

# URL стабильного плейлиста IPTVru
IPTVRU_URL = "https://githubusercontent.com"

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "your_username/your_repo")
USER_NAME, REPO_NAME = GITHUB_REPOSITORY.split("/") if "/" in GITHUB_REPOSITORY else ("username", "repo")
BASE_URL = f"https://{USER_NAME}.github.io/{REPO_NAME}"

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9а-яё\s-]', '', text) # Поддержка кириллицы для slug
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    try:
        response = requests.head(url, timeout=4, allow_redirects=True)
        if response.status_code < 400:
            return True
        response = requests.get(url, timeout=4, stream=True)
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
    
    # Поиск логотипа
    search_names = [channel_name.replace(" ", "").lower(), slugify(channel_name).replace("_", "")]
    for name in search_names:
        test_url = f"https://githubusercontent.com{name}.png"
        try:
            res = requests.get(test_url, timeout=3)
            if res.status_code == 200:
                with open(local_logo_path, 'wb') as f:
                    f.write(res.content)
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    return "https://githubusercontent.com"

def load_external_iptvru():
    """Скачивает и парсит каналы из проекта IPTVru"""
    channels = {}
    print(f"🌐 Скачиваем внешний плейлист IPTVru...")
    try:
        res = requests.get(IPTVRU_URL, timeout=10)
        if res.status_code != 200:
            print("⚠️ Не удалось загрузить IPTVru, используем только локальные каналы.")
            return channels
            
        lines = res.text.splitlines()
        current_inf = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                current_inf = line
            elif line.startswith("http") and current_inf:
                # Извлекаем имя канала (все после последней запятой)
                name_match = re.search(r',([^,]+)$', current_inf)
                name = name_match.group(1).strip() if name_match else "Unknown"
                
                # Извлекаем категорию group-title
                group_match = re.search(r'group-title="([^"]+)"', current_inf)
                group = group_match.group(1).strip() if group_match else "Общие"
                
                # Сохраняем в словарь (ключ — имя канала)
                channels[name] = {"group": group, "url": line}
                current_inf = None
                
        print(f"📊 Успешно импортировано {len(channels)} каналов из IPTVru.")
    except Exception as e:
        print(f"❌ Ошибка парсинга IPTVru: {e}")
    return channels

def main():
    final_channels = {} # Словарь для агрегации: {Имя: {group: ..., url: ...}}

    # 1. Сначала загружаем каналы из IPTVru
    external_channels = load_external_iptvru()
    final_channels.update(external_channels)

    # 2. Затем загружаем локальные ручные каналы (они перезапишут внешние, если совпадут имена)
    print(f"📖 Читаем локальные каналы из {INPUT_FILE}...")
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    name, group, url = parts[0], parts[1], parts[2]
                    final_channels[name] = {"group": group, "url": url} # Перезапись/Добавление
    else:
        print(f"⚠️ Локальный файл {INPUT_FILE} не найден.")

    # 3. Фильтрация, проверка стримов и сборка итогового плейлиста
    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    working_count = 0
    broken_count = 0

    print(f"\n⚡ Начинаем проверку всех каналов (всего: {len(final_channels)})...")
    
    for name, data in final_channels.items():
        url = data["url"]
        group = data["group"]
        
        # Проверяем поток на доступность
        if check_stream(url):
            logo_url = find_and_download_logo(name)
            playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
            playlist_content += f'{url}\n\n'
            working_count += 1
            print(f"✅ Добавлен: {name} [{group}]")
        else:
            broken_count += 1

    # Сохраняем результат
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n🎉 Сборка завершена успешно!")
    print(f"📊 Итог: Рабочих каналов в листе: {working_count}. Отсеяно мертвых ссылок: {broken_count}.")

if __name__ == "__main__":
    main()
