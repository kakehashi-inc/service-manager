#!/usr/bin/env python3
"""
Universal Service Manager
A cross-platform service management tool for custom services/processes.

Supports Linux (Ubuntu/RHEL), macOS, and WSL environments.
"""

import sys
import argparse
from pathlib import Path
from modules.service_manager import ServiceManager


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
        group.add_argument("--all", "-a", action="store_true", help="Apply to all services")

    # サービス定義管理グループ
    management_actions = [("list", "List all services"), ("add", "Add new service"), ("modify", "Modify existing service"), ("delete", "Delete service")]
    for action, desc in management_actions:
        subparser = subparsers.add_parser(action, help=desc)
        if action != "list":
            subparser.add_argument("service_name", help="Service name")

    # 自動起動管理グループ
    autorun_actions = [
        ("enable", "Enable service for auto startup"),
        ("disable", "Disable service from auto startup"),
        ("auto", "Start all auto-enabled services"),
    ]
    for action, desc in autorun_actions:
        subparser = subparsers.add_parser(action, help=desc)
        if action != "auto":
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
    elif args.action == "enable":
        manager.enable_service(args.service_name)
    elif args.action == "disable":
        manager.disable_service(args.service_name)
    elif args.action == "auto":
        success = manager.auto_start_services()
        sys.exit(0 if success else 1)

    sys.exit(0)


if __name__ == "__main__":
    main()
