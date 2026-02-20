import os
import sys
import oracledb
import git
import datetime
from uuid import uuid4
import json
import argparse
import time
import warnings
import zipfile
import requests

warnings.filterwarnings("ignore", category=ResourceWarning)

try:
    import tomllib
except ImportError:
    import tomli as tomllib

CONFIG_FILE = "config.toml"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Конфиг {CONFIG_FILE} не найден!")
        sys.exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)

def get_db_credentials():
    db_user = os.environ.get('DB_USER')
    db_pass = os.environ.get('DB_PASS')
    
    if not db_user or not db_pass:
        print("Ошибка: DB_USER или DB_PASS не установлены в окружении (creds oracle-db-creds)")
        sys.exit(1)
    
    print("Логин/пароль к БД взяты из creds Jenkins (oracle-db-creds)")
    return db_user, db_pass

def checkout_and_pull_branch(repo, branch_name):
    git_user = os.environ.get('GIT_USER')
    git_pass = os.environ.get('GIT_PASS')
    
    if not git_user or not git_pass:
        print("Ошибка: GIT_USER или GIT_PASS не установлены в окружении (creds git_pass)")
        sys.exit(1)
    
    print("Используем git-креды из creds Jenkins (git_pass)")
    
    auth_url = f"https://{git_user}:{git_pass}@git.moscow.alfaintra.net/scm/bialm_ft/bialm_ft_auto.git"
    
    repo.remotes.origin.config_writer.set("url", auth_url)
    
    try:
        print("Выполняем git fetch...")
        repo.remotes.origin.fetch()
        
        remote_branches = {ref.name.split('/')[-1] for ref in repo.remotes.origin.refs}
        
        if branch_name not in remote_branches:
            print(f"Ветка '{branch_name}' не найдена")
            print("Доступные:", ", ".join(sorted(remote_branches)) or "— пусто —")
            sys.exit(1)
        
        print(f"Переключаемся на ветку: {branch_name}")
        repo.git.checkout(branch_name)
        
        print(f"Подтягиваем изменения...")
        repo.git.pull('origin', branch_name)
        
    except git.exc.GitCommandError as e:
        print(f"Ошибка git-команды: {e}")
        print(f"Команда: {e.command}")
        print(f"Вывод ошибки: {e.stderr}")
        sys.exit(1)

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

def main():
    parser = argparse.ArgumentParser(description="Запуск проверки дубликатов по SQL-скриптам")
    parser.add_argument('--branch', required=True, help='Название ветки (обязательно для Jenkins)')
    args = parser.parse_args()

    config = load_config()
    repo_path = "."  # в Jenkins — корень workspace
    
    if not os.path.exists(os.path.join(repo_path, ".git")):
        print("Репозиторий не найден в текущей директории")
        sys.exit(1)
    
    repo = git.Repo(repo_path)
    
    branch_name = args.branch
    checkout_and_pull_branch(repo, branch_name)
    
    tests_dir = os.path.join(repo_path, config["tests"]["tests_directory"])
    sql_files = [f for f in os.listdir(tests_dir) if f.endswith('.sql')]
    
    if not sql_files:
        print("SQL-скрипты не найдены")
        sys.exit(1)
    
    db_user, db_pass = get_db_credentials()
    dsn = config["database"]["default_dsn"]
    
    results = []
    
    print("\nВыполняю проверки...")
    for sql_file in sql_files:
        sql_path = os.path.join(tests_dir, sql_file)
        print(f"→ {sql_file}")
        status, message, details, fname = run_sql_file(sql_path, db_user, db_pass, dsn)
        results.append({"status": status, "message": message, "details": details, "file": fname})
    
    create_allure_results(results, branch_name)
    
    print("\nГотово! Папка allure-results создана.")
    print("Jenkins сам загрузит её в TestOps через withAllureUpload.")

if __name__ == "__main__":
    main()
