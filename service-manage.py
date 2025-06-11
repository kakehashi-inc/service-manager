#!/usr/bin/env python3
"""
Universal Service Manager
A cross-platform service management tool for custom services/processes.

Supports Linux (Ubuntu/RHEL), macOS, and WSL environments.
"""

import json
import os
import sys
import argparse
import subprocess
import signal
import time
from pathlib import Path
from typing import Dict, List, Optional


class ServiceManager:
    """サービス管理ツール"""

    def __init__(self, config_file: str):
        self.config_file = Path(config_file)
        self.config = self._load_config()

        # ディレクトリ設定を取得（設定ファイルの場所を基準とする）
        config_dir = self.config_file.parent if self.config_file.parent != Path(".") else Path(__file__).parent

        log_dir_config = self.config.get("directories", {}).get("logs", "logs")
        pids_dir_config = self.config.get("directories", {}).get("pids", "pids")

        # 相対パスの場合は設定ファイルの場所を基準とする
        if not Path(log_dir_config).is_absolute():
            self.log_dir = config_dir / log_dir_config
        else:
            self.log_dir = Path(log_dir_config)

        if not Path(pids_dir_config).is_absolute():
            self.pids_dir = config_dir / pids_dir_config
        else:
            self.pids_dir = Path(pids_dir_config)

        # ディレクトリを作成
        self.log_dir.mkdir(exist_ok=True)
        self.pids_dir.mkdir(exist_ok=True)

        # 古いログファイルをクリーンアップ
        self._cleanup_old_logs()

    def _load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        if not self.config_file.exists():
            return {"services": {}}

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading config: {e}")
            return {"services": {}}

    def _save_config(self) -> None:
        """設定ファイルを保存"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")

    def _get_service_config(self, service_name: str) -> Optional[Dict]:
        """サービス設定を取得"""
        return self.config.get("services", {}).get(service_name)

    def _save_pid(self, service_name: str, pid: int) -> None:
        """pidファイルを保存"""
        pid_file = self.pids_dir / f"{service_name}.pid"
        try:
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(pid))
        except IOError as e:
            print(f"Warning: Failed to save PID file: {e}")

    def _load_pid(self, service_name: str) -> Optional[int]:
        """pidファイルを読み込み"""
        pid_file = self.pids_dir / f"{service_name}.pid"
        if not pid_file.exists():
            return None

        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except (IOError, ValueError):
            return None

    def _delete_pid_file(self, service_name: str) -> None:
        """pidファイルを削除"""
        pid_file = self.pids_dir / f"{service_name}.pid"
        try:
            if pid_file.exists():
                pid_file.unlink()
        except IOError as e:
            print(f"Warning: Failed to delete PID file: {e}")

    def _is_process_running_by_pid(self, pid: int) -> bool:
        """pidでプロセスが実行中かチェック"""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _cleanup_old_logs(self) -> None:
        """古いログファイルを削除"""
        # 保持する日数を設定から取得（デフォルト: 7日分）
        retention_days = self.config.get("log_retention_days", 7)

        services = self.config.get("services", {})
        if not services:
            return

        for service_name in services.keys():
            # サービスごとのログファイルを取得
            log_pattern = f"{service_name}-*.log"
            log_files = list(self.log_dir.glob(log_pattern))

            if len(log_files) <= retention_days:
                continue  # 保持日数以下の場合はスキップ

            # ファイル名でソート（日付順）
            log_files.sort()

            # 古いファイルを削除（最新のretention_days個を残す）
            files_to_delete = log_files[:-retention_days]
            deleted_count = 0
            for log_file in files_to_delete:
                try:
                    log_file.unlink()
                    deleted_count += 1
                except OSError as e:
                    print(f"Warning: Failed to delete log file {log_file}: {e}")

            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} old log file(s) for service '{service_name}'")

    def _find_process_by_command(self, command: str, args: List[str]) -> List[int]:
        """コマンドライン内容でプロセスを検索"""
        try:
            # プラットフォーム別のpsコマンド
            if sys.platform == "darwin":  # macOS
                cmd = ["ps", "ax", "-o", "pid,command"]
            else:  # Linux/WSL
                cmd = ["ps", "aux"]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return []

            # 検索パターン作成
            search_pattern = f"{command}"
            if args:
                search_pattern += f" {' '.join(args)}"

            pids = []
            for line in result.stdout.split("\n")[1:]:  # ヘッダー行をスキップ
                if search_pattern in line:
                    try:
                        if sys.platform == "darwin":
                            pid = int(line.strip().split()[0])
                        else:
                            parts = line.strip().split()
                            if len(parts) > 1:
                                pid = int(parts[1])
                            else:
                                continue

                        # 自分自身のプロセスは除外
                        if pid != os.getpid():
                            pids.append(pid)
                    except (ValueError, IndexError):
                        continue

            return pids
        except Exception as e:
            print(f"Error finding process: {e}")
            return []

    def start_service(self, service_name: str) -> bool:
        """サービスを開始"""
        config = self._get_service_config(service_name)
        if not config:
            print(f"Error: Service '{service_name}' not found in config.")
            return False

        # サービス設定を取得
        command = config.get("command", "")
        args = config.get("args", [])

        # 既に起動中かチェック
        existing_pid = self._load_pid(service_name)
        if existing_pid and self._is_process_running_by_pid(existing_pid):
            print(f"Service '{service_name}' is already running (PID: {existing_pid})")
            return True
        elif existing_pid:
            # pidファイルはあるがプロセスが存在しない場合は古いpidファイルを削除
            print(f"Removing stale PID file for '{service_name}' (PID: {existing_pid})")
            self._delete_pid_file(service_name)

        # 環境変数設定
        env = os.environ.copy()
        if "env" in config:
            env.update(config["env"])

        # 作業ディレクトリ
        cwd = config.get("cwd")

        # ログファイルパス（日付付き）
        today = time.strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{service_name}-{today}.log"

        print(f"Starting service '{service_name}'...")
        print(f"Command: {command} {' '.join(args)}")
        if cwd:
            print(f"Working directory: {cwd}")
        else:
            print("Working directory: (not set)")

        try:
            # プロセス起動
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- Service started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

                process = subprocess.Popen([command] + args, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=sys.platform != "win32")

            # 起動確認
            time.sleep(2)
            if process.poll() is None:
                # プロセスが正常に開始された場合、pidファイルを保存
                self._save_pid(service_name, process.pid)
                print(f"Service '{service_name}' started successfully (PID: {process.pid})")
                print(f"Log file: {log_file}")
                print(f"PID file: {self.pids_dir / f'{service_name}.pid'}")
                return True
            else:
                print(f"Error: Service '{service_name}' failed to start")
                return False

        except Exception as e:
            print(f"Error starting service '{service_name}': {e}")
            return False

    def stop_service(self, service_name: str) -> bool:
        """サービスを停止"""
        config = self._get_service_config(service_name)
        if not config:
            print(f"Error: Service '{service_name}' not found in config.")
            return False

        # pidファイルからpidを取得
        pid = self._load_pid(service_name)
        if not pid:
            print(f"Service '{service_name}' is not running (no PID file found).")
            return True

        if not self._is_process_running_by_pid(pid):
            print(f"Service '{service_name}' is not running (PID: {pid} not found).")
            # 古いpidファイルを削除
            self._delete_pid_file(service_name)
            return True

        print(f"Stopping service '{service_name}' (PID: {pid})...")

        # プロセスを停止
        try:
            # SIGTERM送信
            if sys.platform != "win32":
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)

            # 終了確認（最大10秒）
            for _ in range(10):
                if not self._is_process_running_by_pid(pid):
                    break
                time.sleep(1)

            # まだ生きている場合はSIGKILL
            if self._is_process_running_by_pid(pid):
                print(f"Force killing process {pid}...")
                if sys.platform != "win32":
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
                time.sleep(1)

        except (OSError, ProcessLookupError):
            pass  # プロセスが既に終了している

        # 最終確認とpidファイル削除
        if not self._is_process_running_by_pid(pid):
            self._delete_pid_file(service_name)
            print(f"Service '{service_name}' stopped successfully.")
            return True
        else:
            print(f"Warning: Process {pid} may still be running.")
            return False

    def restart_service(self, service_name: str) -> bool:
        """サービスを再起動"""
        print(f"Restarting service '{service_name}'...")

        # 停止
        if not self.stop_service(service_name):
            print("Failed to stop service, aborting restart.")
            return False

        # 少し待機
        time.sleep(1)

        # 開始
        return self.start_service(service_name)

    def status_service(self, service_name: str) -> None:
        """サービス状態を表示"""
        config = self._get_service_config(service_name)
        if not config:
            print(f"Service '{service_name}' not found in config.")
            return

        # pidファイルから状態を確認
        pid = self._load_pid(service_name)
        if pid and self._is_process_running_by_pid(pid):
            print(f"{service_name} RUNNING (PID: {pid})")
        elif pid:
            print(f"{service_name} STOPPED (stale PID file: {pid})")
            # 古いpidファイルを削除
            self._delete_pid_file(service_name)
        else:
            print(f"{service_name} STOPPED")

    def start_all_services(self) -> bool:
        """全サービスを開始"""
        services = list(self.config.get("services", {}).keys())
        if not services:
            print("No services configured.")
            return True

        print(f"Starting all services: {', '.join(services)}")
        success = True
        for service_name in services:
            print(f"\n--- {service_name} ---")
            if not self.start_service(service_name):
                success = False
        return success

    def stop_all_services(self) -> bool:
        """全サービスを停止"""
        services = list(self.config.get("services", {}).keys())
        if not services:
            print("No services configured.")
            return True

        print(f"Stopping all services: {', '.join(services)}")
        success = True
        for service_name in services:
            print(f"\n--- {service_name} ---")
            if not self.stop_service(service_name):
                success = False
        return success

    def restart_all_services(self) -> bool:
        """全サービスを再起動"""
        services = list(self.config.get("services", {}).keys())
        if not services:
            print("No services configured.")
            return True

        print(f"Restarting all services: {', '.join(services)}")
        success = True
        for service_name in services:
            print(f"\n--- {service_name} ---")
            if not self.restart_service(service_name):
                success = False
        return success

    def status_all_services(self) -> None:
        """全サービスの状態を表示"""
        services = list(self.config.get("services", {}).keys())
        if not services:
            print("No services configured.")
            return

        print("Status of all services:")
        for service_name in services:
            print(f"\n--- {service_name} ---")
            self.status_service(service_name)

    def list_services(self) -> None:
        """サービス一覧を表示"""
        services = self.config.get("services", {})
        if not services:
            print("No services configured.")
            return

        print("Configured services:")
        for name, config in services.items():
            command = config.get("command", "")
            args = config.get("args", [])

            # pidファイルから状態を確認
            pid = self._load_pid(name)
            if pid and self._is_process_running_by_pid(pid):
                status = f"RUNNING:{pid}"
            else:
                status = "STOPPED"
                # 古いpidファイルがあれば削除
                if pid:
                    self._delete_pid_file(name)

            print(f"  {name:<20} | {status:<12} | {command} {' '.join(args)}")

    def add_service(self, service_name: str) -> None:
        """サービスを追加"""
        if service_name in self.config.get("services", {}):
            print(f"Service '{service_name}' already exists. Use 'modify' to update.")
            return

        print(f"Adding new service: {service_name}")
        config = self._interactive_service_config()

        if not self.config.get("services"):
            self.config["services"] = {}

        self.config["services"][service_name] = config
        self._save_config()
        print(f"Service '{service_name}' added successfully.")

    def modify_service(self, service_name: str) -> None:
        """サービス設定を変更"""
        if service_name not in self.config.get("services", {}):
            print(f"Service '{service_name}' not found.")
            return

        print(f"Modifying service: {service_name}")
        current_config = self.config["services"][service_name]

        print("Current configuration:")
        print(f"  Command: {current_config.get('command', '')}")
        print(f"  Args: {current_config.get('args', [])}")
        print(f"  Working directory: {current_config.get('cwd', '')}")
        print(f"  Environment variables: {current_config.get('env', {})}")

        config = self._interactive_service_config(current_config)
        self.config["services"][service_name] = config
        self._save_config()
        print(f"Service '{service_name}' updated successfully.")

    def delete_service(self, service_name: str) -> None:
        """サービスを削除"""
        if service_name not in self.config.get("services", {}):
            print(f"Service '{service_name}' not found.")
            return

        # 実行中かチェック
        config = self.config["services"][service_name]
        command = config.get("command", "")
        args = config.get("args", [])
        running_pids = self._find_process_by_command(command, args)

        if running_pids:
            print(f"Warning: Service '{service_name}' is currently running.")
            confirm = input("Stop the service and delete? (y/N): ").strip().lower()
            if confirm == "y":
                self.stop_service(service_name)
            else:
                print("Delete cancelled.")
                return

        confirm = input(f"Delete service '{service_name}'? (y/N): ").strip().lower()
        if confirm == "y":
            del self.config["services"][service_name]
            self._save_config()
            print(f"Service '{service_name}' deleted successfully.")
        else:
            print("Delete cancelled.")

    def _interactive_service_config(self, current_config: Optional[Dict] = None) -> Dict:
        """インタラクティブにサービス設定を作成"""
        config = current_config.copy() if current_config else {}

        # コマンド入力
        current_command = config.get("command", "")
        command = input(f"Command [{current_command}]: ").strip()
        if command:
            config["command"] = command
        elif not current_command:
            print("Error: Command is required")
            return self._interactive_service_config(current_config)

        # 引数入力
        args = []
        current_args = config.get("args", [])

        if current_args:
            print(f"Current args: {current_args}")
            modify_args = input("Modify arguments? (y/N/unset): ").strip().lower()
            if modify_args == "unset":
                # unsetが指定された場合は引数設定を削除
                if "args" in config:
                    del config["args"]
            elif modify_args == "y":
                args = self._interactive_args_config(current_args)
                if args:
                    config["args"] = args
                elif "args" in config:
                    del config["args"]  # 空になった場合は削除
        else:
            add_args = input("Add arguments? (y/N): ").strip().lower()
            if add_args == "y":
                args = self._interactive_args_config([])
                if args:
                    config["args"] = args

        # 作業ディレクトリ
        current_cwd = config.get("cwd", "")
        if current_cwd:
            cwd = input(f"Working directory [{current_cwd}] ('unset' to remove): ").strip()
        else:
            cwd = input("Working directory (optional): ").strip()

        if cwd == "unset":
            # unsetが指定された場合は設定を削除
            if "cwd" in config:
                del config["cwd"]
        elif cwd:
            config["cwd"] = cwd

        # 環境変数
        current_env = config.get("env", {})
        if current_env:
            print(f"Current environment variables: {current_env}")
            modify_env = input("Modify environment variables? (y/N/unset): ").strip().lower()
            if modify_env == "unset":
                # unsetが指定された場合は環境変数設定を削除
                if "env" in config:
                    del config["env"]
            elif modify_env == "y":
                new_env = self._interactive_env_config(current_env)
                if new_env:
                    config["env"] = new_env
                elif "env" in config:
                    del config["env"]  # 空になった場合は削除
        else:
            add_env = input("Add environment variables? (y/N): ").strip().lower()
            if add_env == "y":
                new_env = self._interactive_env_config({})
                if new_env:
                    config["env"] = new_env

        return config

    def _interactive_args_config(self, current_args: List[str]) -> List[str]:
        """引数の設定"""
        args = []

        if current_args:
            # 既存引数の編集フェーズ
            print("Edit existing arguments:")
            print("  Enter new value to change, 'unset' to remove, empty line to keep current")

            for i, current_arg in enumerate(current_args):
                new_arg = input(f"  Arg {i} [{current_arg}]: ").strip()
                if new_arg == "unset":
                    # この引数をスキップ（argsに追加しない）
                    pass
                elif new_arg == "":
                    # 空入力の場合は現在の値を保持
                    args.append(current_arg)
                else:
                    # 新しい値に変更
                    args.append(new_arg)

            print("\nAdd new arguments:")
        else:
            # 新規作成の場合
            print("Arguments:")

        # 新規追加フェーズ
        print("  Enter arguments one per line, empty line to finish")
        while True:
            arg_input = input(f"  New arg {len(args)}: ").strip()
            if not arg_input:
                break
            args.append(arg_input)

        return args

    def _interactive_env_config(self, current_env: Dict) -> Dict:
        """環境変数の設定"""
        env = current_env.copy()

        print("Environment variables:")
        print("  Format: KEY=VALUE to set, KEY=unset to remove, empty line to finish")
        if current_env:
            print("  Current variables:")
            for key, value in current_env.items():
                print(f"    {key}={value}")

        while True:
            var = input("  Env var: ").strip()
            if not var:
                break

            if "=" not in var:
                print("  Invalid format. Use KEY=VALUE or KEY=unset")
                continue

            key, value = var.split("=", 1)
            key = key.strip()
            value = value.strip()

            if value.lower() == "unset":
                # unsetが指定された場合は該当のキーを削除
                if key in env:
                    del env[key]
                    print(f"  Removed: {key}")
                else:
                    print(f"  Key '{key}' not found")
            else:
                env[key] = value

        return env


def main():
    parser = argparse.ArgumentParser(description="Universal Service Manager")
    parser.add_argument("--config", help="Config file path (default: config.json)")

    subparsers = parser.add_subparsers(dest="action", help="Available actions")

    # 単体サービス制御グループ
    control_actions = ["start", "stop", "restart", "status"]
    for action in control_actions:
        subparser = subparsers.add_parser(action, help=f"{action.capitalize()} service")
        group = subparser.add_mutually_exclusive_group(required=True)
        group.add_argument("service_name", nargs="?", help="Service name")
        group.add_argument("--all", action="store_true", help="Apply to all services")

    # サービス定義管理グループ
    management_actions = [("list", "List all services"), ("add", "Add new service"), ("modify", "Modify existing service"), ("delete", "Delete service")]
    for action, desc in management_actions:
        subparser = subparsers.add_parser(action, help=desc)
        if action != "list":
            subparser.add_argument("service_name", help="Service name")

    args = parser.parse_args()

    if args.config:
        # 相対パスの場合はカレントディレクトリを基準とする
        if not Path(args.config).is_absolute():
            config_file = Path.cwd() / args.config
        else:
            # 絶対パスの場合はそのまま使用
            config_file = Path(args.config)
    else:
        # 指定のない場合はプログラムのディレクトリにあるconfig.jsonを使用
        config_file = Path(__file__).parent / "config.json"

    if not args.action:
        parser.print_help()
        sys.exit(1)

    manager = ServiceManager(config_file)

    # アクション実行
    if args.action == "start":
        if args.all:
            success = manager.start_all_services()
        else:
            success = manager.start_service(args.service_name)
        sys.exit(0 if success else 1)
    elif args.action == "stop":
        if args.all:
            success = manager.stop_all_services()
        else:
            success = manager.stop_service(args.service_name)
        sys.exit(0 if success else 1)
    elif args.action == "restart":
        if args.all:
            success = manager.restart_all_services()
        else:
            success = manager.restart_service(args.service_name)
        sys.exit(0 if success else 1)
    elif args.action == "status":
        if args.all:
            manager.status_all_services()
        else:
            manager.status_service(args.service_name)
    elif args.action == "list":
        manager.list_services()
    elif args.action == "add":
        manager.add_service(args.service_name)
    elif args.action == "modify":
        manager.modify_service(args.service_name)
    elif args.action == "delete":
        manager.delete_service(args.service_name)

    sys.exit(0)


if __name__ == "__main__":
    main()
