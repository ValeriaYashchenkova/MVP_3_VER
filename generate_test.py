import os
import sys
import getpass
import git
import keyring
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

def get_credentials(service):
    username = keyring.get_password(service, "username")
    password = keyring.get_password(service, "password")
    
    if not username:
        username = input(f"Логин Bitbucket ({service}): ")
        keyring.set_password(service, "username", username)
    
    if not password:
        password = getpass.getpass(f"Пароль Bitbucket ({service}): ")
        keyring.set_password(service, "password", password)
    
    return username, password

def generate_sql_content(schema, table_name, keys_str):
    keys_list = [k.strip() for k in keys_str.split(',')]
    group_by = ', '.join(keys_list)
    sql = f"""-- Проверка дубликатов в таблице {schema}.{table_name}
-- Ключи: {group_by}

SELECT {group_by}, COUNT(*) AS cnt
FROM {schema}.{table_name}
GROUP BY {group_by}
HAVING COUNT(*) > 1
ORDER BY cnt DESC
"""
    return sql.strip()

def main():
    config = load_config()
    
    print("=== Генерация SQL-скрипта на дубликаты ===\n")
    
    schema = input("Схема: ").strip()
    table_name = input("Таблица: ").strip()
    keys = input("Ключи через запятую: ").strip()
    
    sql_content = generate_sql_content(schema, table_name, keys)
    
    tests_dir = config["tests"]["tests_directory"]
    prefix = config["tests"]["test_file_prefix"]
    filename = f"{prefix}{table_name.lower().replace('.', '_')}.sql"
    relative_path = f"{tests_dir}/{filename}"
    full_path = os.path.join(config["repository"]["local_path"], relative_path)
    
    branch_name = input("\nИмя ветки: ").strip()
    
    print("\nСгенерированный SQL:\n" + "="*60)
    print(sql_content)
    print("="*60)
    
    if config["behavior"].get("confirm_before_push", True):
        if not input("\nЗапушить? [y/N]: ").lower().startswith('y'):
            return
    
    git_user, git_pass = get_credentials(config["repository"]["git_service_name"])
    
    repo_path = config["repository"]["local_path"]
    if not os.path.exists(repo_path):
        auth_url = f"https://{git_user}:{git_pass}@{config['repository']['url'].split('https://')[1]}"
        git.Repo.clone_from(auth_url, repo_path)
        print("Репозиторий склонирован")
    
    repo = git.Repo(repo_path)
    
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(sql_content)
    
    repo.remotes.origin.fetch()
    
    if config["behavior"].get("auto_stash", True) and (repo.is_dirty() or repo.untracked_files):
        print("→ stash")
        repo.git.stash('push', '-m', f"auto-stash before {branch_name}")
    
    remote_branches = {ref.name.split('/')[-1] for ref in repo.remotes.origin.refs}
    
    if branch_name in remote_branches:
        repo.git.checkout(branch_name)
        repo.git.pull('origin', branch_name)
    else:
        repo.git.checkout(config["repository"]["default_branch"])
        repo.git.pull('origin', config["repository"]["default_branch"])
        repo.git.checkout('-b', branch_name)
    
    repo.git.add(relative_path)
    repo.index.commit(f"Add duplicate check SQL for {schema}.{table_name}")
    repo.git.push('--set-upstream', 'origin', branch_name)
    
    print(f"\nГотово! Файл: {relative_path}")
    print(f"Ветка: {branch_name}")

if __name__ == "__main__":
    main()
