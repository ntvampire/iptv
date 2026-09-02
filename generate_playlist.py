import os
import re
import requests

INPUT_FILE = "input_channels.txt"
OUTPUT_FILE = "index.m3u"
LOGOS_DIR = "logos"
EPG_URL = "http://teleguide.info"

# Базовый URL вашего сайта на GitHub Pages (изменится автоматически скриптом или укажите свой)
# Скрипт попытается определить его по переменным окружения GitHub
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "your_username/your_repo")
USER_NAME, REPO_NAME = GITHUB_REPOSITORY.split("/") if "/" in GITHUB_REPOSITORY else ("username", "repo")
BASE_URL = f"https://{USER_NAME}.github.io/{REPO_NAME}"

# Открытая база логотипов для автоматического поиска
LOGOS_SOURCE_URL = "https://githubusercontent.com"

def slugify(text):
    """Преобразует название канала в безопасное имя файла (например, 'Trace Urban' -> 'trace_urban')"""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '_', text)

def check_stream(url):
    """Проверяет работоспособность потока. Возвращает True, если поток активен."""
    try:
        # Для потоков IPTV запрашиваем только заголовки (HEAD), чтобы не качать видеофайл целиком
        # Ставим таймаут 5 секунд, чтобы скрипт не зависал на мертвых ссылках
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code in:
            return True
        # Если HEAD запрещен сервером, пробуем быстрый GET (первые пару байт)
        response = requests.get(url, timeout=5, stream=True)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False

def find_and_download_logo(channel_name):
    """Ищет логотип канала в публичных источниках и сохраняет локально"""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    logo_filename = f"{slugify(channel_name)}.png"
    local_logo_path = os.path.join(LOGOS_DIR, logo_filename)
    
    # Если логотип уже скачан ранее, просто возвращаем ссылку на него
    if os.path.exists(local_logo_path):
        return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
    
    print(f"🔍 Ищем логотип для: {channel_name}...")
    
    # Список возможных вариантов написания названия канала для поиска в базе iptv-org
    search_names = [
        channel_name.replace(" ", "").lower(),
        slugify(channel_name).replace("_", ""),
        channel_name.lower().split(" ")[0] # Пробуем первое слово (например, 'trace')
    ]
    
    # База логотипов ://github.com
    # Пробуем найти прямым перебором в популярном архиве
    for name in search_names:
        test_url = f"https://githubusercontent.com{name}.png"
        try:
            res = requests.get(test_url, timeout=5)
            if res.status_code == 200:
                with open(local_logo_path, 'wb') as f:
                    f.write(res.content)
                print(f"📥 Логотип успешно скачан и сохранен: {local_logo_path}")
                return f"{BASE_URL}/{LOGOS_DIR}/{logo_filename}"
        except Exception:
            continue
            
    # Заглушка, если логотип вообще не найден в интернете
    print(f"⚠️ Логотип для '{channel_name}' не найден. Будет использована иконка по умолчанию.")
    return "https://githubusercontent.com"

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Файл {INPUT_FILE} не найден!")
        return

    playlist_content = f'#EXTM3U x-tvg-url="{EPG_URL}"\n\n'
    working_count = 0
    broken_count = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            try:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue
                
                name, group, url = parts[0], parts[1], parts[2]
                
                print(f"📺 Проверяем канал: {name}...")
                if check_stream(url):
                    print(f"✅ Поток работает.")
                    logo_url = find_and_download_logo(name)
                    
                    playlist_content += f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n'
                    playlist_content += f'{url}\n\n'
                    working_count += 1
                else:
                    print(f"❌ Поток НЕ работает. Пропускаем.")
                    broken_count += 1
                    
            except Exception as e:
                print(f"Ошибка строки: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(playlist_content)
        
    print(f"\n📊 Итоги сборки: Рабочих каналов: {working_count}, Удалено мертвых: {broken_count}.")

if __name__ == "__main__":
    main()
