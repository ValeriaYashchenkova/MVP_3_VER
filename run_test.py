# run_test.py (или run_test_allure.py)
import os
import sys
import oracledb
import git
import datetime
import requests
import zipfile
import argparse
import time
import warnings
warnings.filterwarnings("ignore", category=ResourceWarning)  # убирает предупреждение WinError 6

try:
    import tomllib
except ImportError:
    import tomli as tomllib

CONFIG_FILE = "config.toml"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Ошибка: файл {CONFIG_FILE} не найден!")
        print("Создай его рядом со скриптом с секциями [database] и [testops]")
        sys.exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)

def get_db_credentials(config):
    db_user = config.get("database", {}).get("db_user")
    db_password = config.get("database", {}).get("db_password")
    
    if not db_user or not db_password:
        print("Ошибка: в config.toml в секции [database] отсутствуют db_user или db_password")
        print("Пример:")
        print("[database]")
        print("db_user = \"твой_логин\"")
        print("db_password = \"твой_пароль\"")
        sys.exit(1)
    
    print("Используем логин/пароль из config.toml")
    return db_user, db_password

def checkout_and_pull_branch(repo, branch_name):
    repo.remotes.origin.fetch()
    remote_branches = {ref.name.split('/')[-1] for ref in repo.remotes.origin.refs}
    
    if branch_name not in remote_branches:
        print(f"Ветка '{branch_name}' не найдена")
        print("Доступные:", ", ".join(sorted(remote_branches)) or "— пусто —")
        sys.exit(1)
    
    print(f"Переключаемся на ветку: {branch_name}")
    repo.git.checkout(branch_name)
    print(f"Подтягиваем изменения: git pull origin {branch_name}")
    repo.git.pull('origin', branch_name)

def run_sql_file(sql_path, db_user, db_pass, dsn):
    file_name = os.path.basename(sql_path)
    status = "passed"
    message = "OK — дубликатов не найдено"
    details = ""
    
    try:
        conn = oracledb.connect(user=db_user, password=db_pass, dsn=dsn)
        cursor = conn.cursor()
        sql = open(sql_path, 'r', encoding='utf-8').read().rstrip(' \n;')
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        if rows:
            status = "failed"
            message = f"Найдено {len(rows)} наборов дубликатов"
            details = "\n".join(str(row) for row in rows)
        
        conn.close()
    except oracledb.Error as e:
        status = "broken"
        message = "Ошибка выполнения"
        details = str(e)
    
    return status, message, details, file_name

def create_allure_results(results, branch_name):
    allure_dir = "allure-results"
    os.makedirs(allure_dir, exist_ok=True)
    
    from uuid import uuid4
    import json
    
    for r in results:
        test_uuid = str(uuid4())
        test_file = os.path.join(allure_dir, f"{test_uuid}-result.json")
        
        status_map = {"passed": "passed", "failed": "failed", "broken": "broken"}
        
        attachments = []
        if r["details"]:
            attach_filename = f"{test_uuid}-details.txt"
            attach_path = os.path.join(allure_dir, attach_filename)
            with open(attach_path, 'w', encoding='utf-8') as f:
                f.write(r["details"])
            attachments = [{"name": "Детали", "source": attach_filename, "type": "text/plain"}]
        
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump({
                "name": r["file"],
                "description": r["message"],
                "status": status_map.get(r["status"], "broken"),
                "steps": [{"name": "Выполнение SQL", "status": status_map.get(r["status"], "broken")}],
                "attachments": attachments,
                "labels": [{"name": "branch", "value": branch_name}],
                "uuid": test_uuid,
                "start": int(datetime.datetime.now().timestamp() * 1000),
                "stop": int(datetime.datetime.now().timestamp() * 1000)
            }, f, ensure_ascii=False)

def upload_to_testops(allure_results_dir, config, skip_upload=False):
    if skip_upload:
        print("Режим без загрузки: zip создан, но не отправлен")
        return True
    
    project_id = config.get("testops", {}).get("project_id")
    token = config.get("testops", {}).get("launch_token")
    base_url = config.get("testops", {}).get("url", "https://testops.moscow.alfaintra.net")
    
    if not project_id or not token:
        print("Ошибка: в config.toml отсутствует секция [testops] или поля project_id / launch_token")
        return False
    
    zip_path = "allure-results.zip"
    
    print(f"Архивирую папку {allure_results_dir} → {zip_path}")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(allure_results_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, allure_results_dir)
                    zipf.write(file_path, arcname)
                    print(f"  + {arcname}")
        
        url = f"{base_url}/api/launch/upload"
        headers = {"Authorization": f"Api-Token {token}"}
        params = {"projectId": project_id}
        
        print(f"\nОтправка POST на: {url}")
        print(f"Параметры: projectId={project_id}")
        
        with open(zip_path, "rb") as zip_file:
            files = {"file": ("allure-results.zip", zip_file, "application/zip")}
            
            response = requests.post(
                url,
                headers=headers,
                params=params,
                files=files,
                timeout=120,
                verify=False
            )
        
        response.raise_for_status()
        
        data = response.json()
        launch_url = data.get("launchUrl") or data.get("url") or data.get("location", "ссылка не получена")
        
        print("\n=== УСПЕХ ===")
        print("Результаты загружены в TestOps")
        print(f"Ссылка на запуск: {launch_url}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\nОшибка HTTP-запроса: {e}")
        if 'response' in locals():
            print(f"Код ответа: {response.status_code}")
            print("Текст ответа:", response.text)
        return False
        
    except Exception as e:
        print("\nНеизвестная ошибка при загрузке:", str(e))
        return False
        
    finally:
        if os.path.exists(zip_path):
            for attempt in range(3):
                try:
                    time.sleep(0.5 * attempt)
                    os.remove(zip_path)
                    print(f"Zip удалён: {zip_path}")
                    break
                except PermissionError:
                    print(f"Zip занят ({attempt+1}/3)...")
                except Exception as rm_err:
                    print(f"Не удалось удалить zip: {rm_err}")
                    break

def main():
    parser = argparse.ArgumentParser(description="Запуск проверки дубликатов по SQL-скриптам")
    parser.add_argument('--branch', help='Название ветки (опционально)')
    parser.add_argument('--no-upload', action='store_true', help='Не загружать в TestOps (только локально)')
    args = parser.parse_args()

    config = load_config()
    repo_path = "."  # текущая директория (workspace Jenkins)
    
    if not os.path.exists(repo_path):
        print("Репозиторий не найден. Запустите generate_test.py")
        sys.exit(1)
    
    repo = git.Repo(repo_path)
    
    branch_name = args.branch or input("Название ветки: ").strip()
    checkout_and_pull_branch(repo, branch_name)
    
    tests_dir = os.path.join(repo_path, config["tests"]["tests_directory"])
    sql_files = [f for f in os.listdir(tests_dir) if f.endswith('.sql')]
    
    if not sql_files:
        print("SQL-скрипты не найдены")
        return
    
    db_user, db_pass = get_db_credentials(config)
    dsn = config["database"]["default_dsn"]
    
    results = []
    
    print("\nВыполняю проверки...")
    for sql_file in sql_files:
        sql_path = os.path.join(tests_dir, sql_file)
        print(f"→ {sql_file}")
        status, message, details, fname = run_sql_file(sql_path, db_user, db_pass, dsn)
        results.append({"status": status, "message": message, "details": details, "file": fname})
    
    create_allure_results(results, branch_name)
    
    upload_to_testops("allure-results", config, skip_upload=args.no_upload)

if __name__ == "__main__":
    main()
