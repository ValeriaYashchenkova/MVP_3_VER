import os
import sys
import oracledb
import datetime
from uuid import uuid4
import json
import argparse
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

try:
    import tomllib
except ImportError:
    import tomli as tomllib

CONFIG_FILE = "config.toml"


# ---------------- CONFIG ----------------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Конфиг {CONFIG_FILE} не найден!")
        sys.exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


# ---------------- DB CREDS ----------------
def get_db_credentials():
    db_user = os.environ.get('DB_USER')
    db_pass = os.environ.get('DB_PASS')

    if not db_user or not db_pass:
        print("Ошибка: DB_USER или DB_PASS не установлены в окружении Jenkins")
        sys.exit(1)

    print("✔ DB креды получены из Jenkins")
    return db_user, db_pass


# ---------------- SQL RUN ----------------
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


# ---------------- ALLURE ----------------
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
                "labels": [{"name": "branch", "value": branch_name}],
                "uuid": test_uuid,
                "start": int(datetime.datetime.now().timestamp() * 1000),
                "stop": int(datetime.datetime.now().timestamp() * 1000)
            }, f, ensure_ascii=False)


# ---------------- MAIN ----------------
def main():
    parser = argparse.ArgumentParser(description="Запуск SQL проверок")
    parser.add_argument('--branch', required=True)
    args = parser.parse_args()

    print(f"Jenkins checkout ветки: {args.branch}")

    config = load_config()
    repo_path = "."

    tests_dir = os.path.join(repo_path, config["tests"]["tests_directory"])

    if not os.path.exists(tests_dir):
        print("Папка с SQL тестами не найдена:", tests_dir)
        sys.exit(1)

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

    create_allure_results(results, args.branch)

    print("\nГотово! Allure results сформированы.")


if __name__ == "__main__":
    main()
