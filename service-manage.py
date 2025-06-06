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

    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.config = self._load_config()

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

    def _is_process_running(self, pid: int) -> bool:
        """プロセスが実行中かチェック"""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _get_log_tail(self, service_name: str, lines: int = 5) -> List[str]:
        """ログファイルの末尾を取得"""
        log_file = self.log_dir / f"{service_name}.log"
        if not log_file.exists():
            return ["No log file found"]

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                return [line.rstrip() for line in all_lines[-lines:]]
        except IOError:
            return ["Error reading log file"]

    def start_service(self, service_name: str) -> bool:
        """サービスを開始"""
        config = self._get_service_config(service_name)
        if not config:
            print(f"Error: Service '{service_name}' not found in config.")
            return False

        # 既に起動中かチェック
        command = config.get("command", "")
        args = config.get("args", [])
        running_pids = self._find_process_by_command(command, args)

        if running_pids:
            print(f"Service '{service_name}' is already running (PID: {running_pids[0]})")
            return True

        # 環境変数設定
        env = os.environ.copy()
        if "env" in config:
            env.update(config["env"])

        # 作業ディレクトリ
        cwd = config.get("cwd", ".")

        # ログファイルパス
        log_file = self.log_dir / f"{service_name}.log"

        print(f"Starting service '{service_name}'...")
        print(f"Command: {command} {' '.join(args)}")
        print(f"Working directory: {cwd}")

        try:
            # プロセス起動
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- Service started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

                process = subprocess.Popen([command] + args, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=sys.platform != "win32")

            # 起動確認
            time.sleep(2)
            if process.poll() is None:
                print(f"Service '{service_name}' started successfully (PID: {process.pid})")
                print(f"Log file: {log_file}")
                return True
            else:
                print(f"Error: Service '{service_name}' failed to start")
                print("Recent log entries:")
                for line in self._get_log_tail(service_name, 3):
                    print(f"  {line}")
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

        command = config.get("command", "")
        args = config.get("args", [])
        running_pids = self._find_process_by_command(command, args)

        if not running_pids:
            print(f"Service '{service_name}' is not running.")
            return True

        print(f"Stopping service '{service_name}' (PID: {running_pids[0]})...")

        # 各プロセスを停止
        for pid in running_pids:
            try:
                # SIGTERM送信
                if sys.platform != "win32":
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)

                # 終了確認（最大10秒）
                for _ in range(10):
                    if not self._is_process_running(pid):
                        break
                    time.sleep(1)

                # まだ生きている場合はSIGKILL
                if self._is_process_running(pid):
                    print(f"Force killing process {pid}...")
                    if sys.platform != "win32":
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                    time.sleep(1)

            except (OSError, ProcessLookupError):
                pass  # プロセスが既に終了している

        # 最終確認
        remaining_pids = self._find_process_by_command(command, args)
        if not remaining_pids:
            print(f"Service '{service_name}' stopped successfully.")
            return True
        else:
            print(f"Warning: Some processes may still be running: {remaining_pids}")
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

        command = config.get("command", "")
        args = config.get("args", [])
        running_pids = self._find_process_by_command(command, args)

        print(f"Service: {service_name}")
        print(f"Command: {command} {' '.join(args)}")

        if running_pids:
            print(f"Status: RUNNING (PID: {', '.join(map(str, running_pids))})")
        else:
            print("Status: STOPPED")

        # ログの末尾を表示
        print("\nRecent log entries:")
        log_entries = self._get_log_tail(service_name, 5)
        for entry in log_entries:
            print(f"  {entry}")

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

        print(f"Status of all services:")
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
            running_pids = self._find_process_by_command(command, args)
            status = "RUNNING" if running_pids else "STOPPED"
            print(f"  {name:<20} | {status:<8} | {command} {' '.join(args)}")

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
        print(f"  Working directory: {current_config.get('cwd', '.')}")
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
        print("Arguments (enter empty line to finish):")
        args = []
        current_args = config.get("args", [])

        if current_args:
            print(f"Current args: {current_args}")
            use_current = input("Keep current args? (Y/n): ").strip().lower()
            if use_current != "n":
                args = current_args
            else:
                while True:
                    arg = input("  Arg: ").strip()
                    if not arg:
                        break
                    args.append(arg)
        else:
            while True:
                arg = input("  Arg: ").strip()
                if not arg:
                    break
                args.append(arg)

        config["args"] = args

        # 作業ディレクトリ
        current_cwd = config.get("cwd", ".")
        cwd = input(f"Working directory [{current_cwd}]: ").strip()
        if cwd:
            config["cwd"] = cwd
        elif "cwd" not in config:
            config["cwd"] = "."

        # 環境変数
        current_env = config.get("env", {})
        if current_env:
            print(f"Current environment variables: {current_env}")
            modify_env = input("Modify environment variables? (y/N): ").strip().lower()
            if modify_env == "y":
                config["env"] = self._interactive_env_config(current_env)
            else:
                config["env"] = current_env
        else:
            add_env = input("Add environment variables? (y/N): ").strip().lower()
            if add_env == "y":
                config["env"] = self._interactive_env_config({})

        return config

    def _interactive_env_config(self, current_env: Dict) -> Dict:
        """環境変数の設定"""
        env = current_env.copy()

        print("Environment variables (format: KEY=VALUE, empty line to finish):")
        while True:
            var = input("  Env var: ").strip()
            if not var:
                break

            if "=" not in var:
                print("  Invalid format. Use KEY=VALUE")
                continue

            key, value = var.split("=", 1)
            env[key.strip()] = value.strip()

        return env


def main():
    parser = argparse.ArgumentParser(description="Universal Service Manager")
    parser.add_argument("--config", default="config.json", help="Config file path")

    subparsers = parser.add_subparsers(dest="action", help="Available actions")

    # 単体サービス制御グループ (--all オプション有り)
    control_actions = ["start", "stop", "restart", "status"]
    for action in control_actions:
        subparser = subparsers.add_parser(action, help=f"{action.capitalize()} service")
        group = subparser.add_mutually_exclusive_group(required=True)
        group.add_argument("service_name", nargs="?", help="Service name")
        group.add_argument("--all", action="store_true", help="Apply to all services")

    # サービス定義管理グループ (--all オプション無し)
    management_actions = [("list", "List all services"), ("add", "Add new service"), ("modify", "Modify existing service"), ("delete", "Delete service")]
    for action, desc in management_actions:
        subparser = subparsers.add_parser(action, help=desc)
        if action != "list":
            subparser.add_argument("service_name", help="Service name")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    manager = ServiceManager(args.config)

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
