import os
import sys
import oracledb
import git
import datetime
from uuid import uuid4
import json
import argparse
import urllib.parse
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


# ---------------- CREDS ----------------
def resolve_cred(cli_val, env_name):
    return cli_val if cli_val else os.environ.get(env_name)


def get_db_credentials(args):
    db_user = resolve_cred(args.db_user, "DB_USER")
    db_pass = resolve_cred(args.db_pass, "DB_PASS")

    if not db_user or not db_pass:
        print("Ошибка: DB_USER или DB_PASS не переданы")
        sys.exit(1)

    print("✔ DB креды получены")
    return db_user, db_pass


def get_git_credentials(args):
    git_user = resolve_cred(args.git_user, "GIT_USER")
    git_pass = resolve_cred(args.git_pass, "GIT_PASS")

    if not git_user or not git_pass:
        print("Ошибка: GIT_USER или GIT_PASS не переданы")
        sys.exit(1)

    print("✔ Git креды получены")
    return git_user, git_pass


# ---------------- GIT ----------------
def checkout_and_pull_branch(repo, branch_name, git_user, git_pass):
    git_user = urllib.parse.quote(git_user)
    git_pass = urllib.parse.quote(git_pass)

    auth_url = f"https://{git_user}:{git_pass}@git.moscow.alfaintra.net/scm/bialm_ft/bialm_ft_auto.git"

    repo.remotes.origin.set_url(auth_url)

    try:
        print("git fetch...")
        repo.remotes.origin.fetch(prune=True)

        remote_branches = {ref.name.split('/')[-1] for ref in repo.remotes.origin.refs}

        if branch_name not in remote_branches:
            print(f"Ветка '{branch_name}' не найдена")
            print("Доступные:", ", ".join(sorted(remote_branches)) or "— пусто —")
            sys.exit(1)

        print(f"checkout {branch_name}")
        repo.git.checkout(branch_name)
        repo.git.pull('origin', branch_name)

    except git.exc.GitCommandError as e:
        print("Git ошибка:")
        print(e.stderr)
        sys.exit(1)


# ---------------- MAIN ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', required=True)
    parser.add_argument('--git-user')
    parser.add_argument('--git-pass')
    parser.add_argument('--db-user')
    parser.add_argument('--db-pass')
    args = parser.parse_args()

    config = load_config()
    repo = git.Repo(".")

    git_user, git_pass = get_git_credentials(args)
    checkout_and_pull_branch(repo, args.branch, git_user, git_pass)

    db_user, db_pass = get_db_credentials(args)
    dsn = config["database"]["default_dsn"]

    print("Подключение к Oracle...")
    conn = oracledb.connect(user=db_user, password=db_pass, dsn=dsn)
    print("✔ Oracle OK")
    conn.close()

    print("Готово!")


if __name__ == "__main__":
    main()
