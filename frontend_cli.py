# --- START OF FILE frontend_cli.py ---

import sys
import os
import asyncio
import tkinter as tk
from tkinter import messagebox, scrolledtext
import webbrowser
from pathlib import Path
import json

try:
    # --- FIXED: Import CURRENT_VERSION directly ---
    from backend import CaiBackend, CURRENT_VERSION
except ImportError:
    print("致命错误: backend.py 文件缺失。请确保两个文件都在同一个目录下。")
    sys.exit(1)

try:
    from colorama import init as colorama_init, Fore, Back, Style
    colorama_init()
except ImportError:
    class DummyStyle:
        def __getattr__(self, name): return ""
    Fore = Back = Style = DummyStyle()


def show_info_dialog():
    settings_path = Path('./settings.json')
    if settings_path.exists():
        try:
            if not json.loads(settings_path.read_text(encoding='utf-8')).get('show_notification', True):
                return
        except Exception:
            pass

    root = tk.Tk()
    root.title("Cai Downloader 信息提示")
    window_width, window_height = 400, 200
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    pos_x = int(screen_width / 2 - window_width / 2)
    pos_y = int(screen_height / 2 - window_height / 2)
    root.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
    root.resizable(False, False)
    tk.Label(root, text="欢迎使用 Cai Downloader!\n官方Q群:993782526\n作者B站: 菜Games-pvzcxw",
             font=("Arial", 12)).pack(pady=20)
    dont_show = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text="不再显示此消息", variable=dont_show, font=("Arial", 10)).pack(pady=5)
    def on_confirm():
        if dont_show.get():
            try:
                settings_path.write_text(json.dumps({'show_notification': False}, indent=2), encoding='utf-8')
            except Exception as e: print(f"保存设置失败: {e}")
        root.destroy()
    tk.Button(root, text="确认", width=10, command=on_confirm, font=("Arial", 10)).pack(pady=10)
    root.bind('<Return>', lambda event: on_confirm())
    root.mainloop()

# --- MODIFIED: Updated banner for Downloader ---
def show_banner(backend: CaiBackend):
    log = backend.log
    log.info(f"Cai Downloader v{CURRENT_VERSION.split('-')[0]} ")
    log.info('软件作者:pvzcxw')
    log.warning('菜Games出品 本项目完全免费，作者b站:菜Games-pvzcxw,请多多赞助使用')
    log.warning('官方Q群:993782526')
    log.warning('本工具用于下载游戏清单(.manifest)及生成解锁文件(.lua)。')
    log.info('App ID可以在SteamDB, SteamUI或Steam商店链接页面查看')


# --- MODIFIED: Removed SteamTools specific questions ---
async def main_flow(backend: CaiBackend):
    log = backend.log
    try:
        app_id_input = input(
            f"{Fore.CYAN}{Back.BLACK}{Style.BRIGHT}请输入游戏AppID、steamdb/steam链接或游戏名称(多个请用英文逗号分隔): {Style.RESET_ALL}").strip()
        if not app_id_input:
            log.error("输入不能为空。")
            return
        input_items = [item.strip() for item in app_id_input.split(',')]
    except (EOFError, KeyboardInterrupt):
        log.warning("\n操作已取消。")
        return

    add_all_dlc = False
    patch_depot_key = False

    # ---------- 1. 是否下载全部 DLC ----------
    print(f"\n{Fore.YELLOW}附加功能:{Style.RESET_ALL}")
    choice = input(f"{Fore.GREEN}是否额外添加该游戏的所有可用 DLC? (y/n) [默认: y]: {Style.RESET_ALL}").strip().lower()
    if choice in ('y', 'yes', '是', ''):
        add_all_dlc = True
        print(f"{Fore.GREEN}已启用: 额外添加所有可用 DLC。{Style.RESET_ALL}")
    else:
        add_all_dlc = False
        print(f"{Fore.GREEN}已跳过: 额外添加 DLC。{Style.RESET_ALL}")

    # ---------- 2. 是否修补创意工坊密钥 ----------
    print(f"\n{Fore.YELLOW}创意工坊密钥修补功能:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}此功能会自动下载该游戏的创意工坊密钥并添加到.lua文件中。{Style.RESET_ALL}")
    choice = input(f"{Fore.GREEN}是否修补创意工坊密钥? (y/n) [默认: y]: {Style.RESET_ALL}").strip().lower()
    if choice in ('y', 'yes', '是', ''):
        patch_depot_key = True
        print(f"{Fore.GREEN}已启用: 创意工坊密钥修补。{Style.RESET_ALL}")
    else:
        patch_depot_key = False
        print(f"{Fore.GREEN}已跳过: 创意工坊密钥修补。{Style.RESET_ALL}")

    print(f"\n{Fore.YELLOW}请选择清单查找方式：")
    print(f"{Fore.CYAN}1. 从指定清单库中选择")
    print(f"{Fore.CYAN}2. 在所有GitHub清单库中搜索{Style.RESET_ALL}")

    try:
        search_choice_input = input(f"{Fore.GREEN}请输入数字选择查找方式: {Style.RESET_ALL}")
        if not search_choice_input.isdigit():
            log.error("无效选择，请输入数字。")
            return
        search_choice = int(search_choice_input)
    except (ValueError, EOFError, KeyboardInterrupt):
        log.error("无效选择或操作已取消。")
        return

    if search_choice == 1:
        await handle_repo_selection(backend, input_items, add_all_dlc, patch_depot_key)
    elif search_choice == 2:
        await handle_github_search(backend, input_items, add_all_dlc, patch_depot_key)
    else:
        log.error("无效的选择，请输入1或2。")


async def handle_repo_selection(backend: CaiBackend, items: list, add_all_dlc: bool, patch_depot_key: bool):
    log = backend.log
    print(f"\n{Fore.YELLOW}请选择清单库：")
    builtin_zip_repos = {
        1: ("SWA V2库", lambda app_id: backend.process_printedwaste_manifest(app_id, add_all_dlc, patch_depot_key)),
        2: ("Cysaw库", lambda app_id: backend.process_cysaw_manifest(app_id, add_all_dlc, patch_depot_key)),
        3: ("Furcate库", lambda app_id: backend.process_furcate_manifest(app_id, add_all_dlc, patch_depot_key)),
        4: ("Walftech库", lambda app_id: backend.process_walftech_manifest(app_id, add_all_dlc, patch_depot_key)),
        5: ("SteamDatabase库", lambda app_id: backend.process_steamdatabase_manifest(app_id, add_all_dlc, patch_depot_key)),
        6: ("SteamAutoCracks/ManifestHub(v2)", lambda app_id: backend.process_steamautocracks_v2_manifest(app_id, add_all_dlc, patch_depot_key)),
        7: ("清单不求人（仅清单）", lambda app_id: backend.process_buqiuren_manifest(app_id))
    }
    current_index, repo_handlers = 1, {}
    for i, (name, handler) in builtin_zip_repos.items():
        print(f"{Fore.CYAN}{current_index}. {name}")
        repo_handlers[current_index] = ('builtin_zip', handler)
        current_index += 1
    if custom_zip_repos := backend.get_custom_zip_repos():
        print(f"{Fore.MAGENTA}--- 自定义ZIP清单库 ---")
        for repo_config in custom_zip_repos:
            print(f"{Fore.MAGENTA}{current_index}. {repo_config['name']} (自定义)")
            repo_handlers[current_index] = ('custom_zip', repo_config)
            current_index += 1
    builtin_github_repos = ['Auiowu/ManifestAutoUpdate', 'SteamAutoCracks/ManifestHub']
    print(f"{Fore.GREEN}--- GitHub清单库 ---")
    for repo in builtin_github_repos:
        print(f"{Fore.GREEN}{current_index}. {repo}")
        repo_handlers[current_index] = ('builtin_github', repo)
        current_index += 1
    if custom_github_repos := backend.get_custom_github_repos():
        for repo_config in custom_github_repos:
            print(f"{Fore.GREEN}{current_index}. {repo_config['name']} ({repo_config['repo']}) (自定义)")
            repo_handlers[current_index] = ('custom_github', repo_config['repo'])
            current_index += 1
    print(f"{Style.RESET_ALL}")
    try:
        choice = int(input(f"{Fore.GREEN}请输入数字选择清单库: {Style.RESET_ALL}"))
    except (ValueError, EOFError, KeyboardInterrupt):
        log.error("无效选择或操作已取消。"); return
    if choice not in repo_handlers:
        log.error(f"无效的库选择: {choice}"); return
    
    repo_type, repo_data = repo_handlers[choice]
    is_github_choice = repo_type in ['builtin_github', 'custom_github']
    await backend.checkcn()
    if is_github_choice and not await backend.check_github_api_rate_limit(): return

    for item in items:
        app_id = backend.extract_app_id(item)
        if not app_id:
            log.info(f"'{item}' 不是一个有效的AppID, 正在按游戏名称搜索...")
            games = await backend.find_appid_by_name(item)
            if not games:
                log.error(f"未找到名为 '{item}' 的游戏。"); continue
            log.info("找到以下匹配的游戏:")
            for i, game in enumerate(games, 1):
                log.info(f"{i}. {game.get('schinese_name') or game.get('name', 'N/A')} (AppID: {game['appid']})")
            try:
                choice = int(input("请选择游戏编号: ")) - 1
                if 0 <= choice < len(games): app_id = games[choice]['appid']
                else: log.error("无效选择。"); continue
            except (ValueError, EOFError, KeyboardInterrupt):
                log.error("无效输入或操作已取消。"); continue
        
        log.info(f"--- 开始处理 AppID: {app_id} ---")
        success = False
        if repo_type == 'builtin_zip': success = await repo_data(app_id)
        elif repo_type == 'custom_zip': success = await backend.process_custom_zip_manifest(app_id, repo_data, add_all_dlc, patch_depot_key)
        elif repo_type == 'builtin_github': success = await backend.process_github_manifest(app_id, repo_data, add_all_dlc, patch_depot_key)
        elif repo_type == 'custom_github': success = await backend.process_github_manifest(app_id, repo_data, add_all_dlc, patch_depot_key)
        log.info(f"--- AppID {app_id} 处理 {'成功' if success else '失败'} ---\n")

async def handle_github_search(backend: CaiBackend, items: list, add_all_dlc: bool, patch_depot_key: bool):
    log = backend.log
    await backend.checkcn()
    if not await backend.check_github_api_rate_limit(): return
    
    all_github_repos = backend.get_all_github_repos()
    log.info(f"将在以下 {len(all_github_repos)} 个GitHub仓库中搜索:")
    for repo in ['Auiowu/ManifestAutoUpdate', 'SteamAutoCracks/ManifestHub']: log.info(f"  - {repo} (内置)")
    for repo in [r['repo'] for r in backend.get_custom_github_repos()]: log.info(f"  - {repo} (自定义)")
    
    for item in items:
        app_id = backend.extract_app_id(item)
        if not app_id:
            log.info(f"'{item}' 不是一个有效的AppID, 正在按游戏名称搜索...")
            games = await backend.find_appid_by_name(item)
            if not games: log.error(f"未找到名为 '{item}' 的游戏。"); continue
            log.info("找到以下匹配的游戏:")
            for i, game in enumerate(games, 1): log.info(f"{i}. {game.get('schinese_name') or game.get('name', 'N/A')} (AppID: {game['appid']})")
            try:
                choice = int(input("请选择游戏编号: ")) - 1
                if 0 <= choice < len(games): app_id = games[choice]['appid']
                else: log.error("无效选择。"); continue
            except (ValueError, EOFError, KeyboardInterrupt):
                log.error("无效输入或操作已取消。"); continue
        
        log.info(f"--- 开始为 AppID {app_id} 搜索 GitHub 清单 ---")
        results = await backend.search_all_repos_for_appid(app_id, all_github_repos)
        if not results:
            log.error(f"在所有 GitHub 仓库中都未找到 AppID {app_id} 的清单。"); continue
        log.info(f"在以下仓库中找到清单：")
        for i, res in enumerate(results, 1):
            repo_display = f"{res['repo']} (自定义)" if res['repo'] not in ['Auiowu/ManifestAutoUpdate', 'SteamAutoCracks/ManifestHub'] else res['repo']
            print(f"{Fore.CYAN}{i}. {repo_display} (更新时间: {res['update_date']}){Style.RESET_ALL}")
        try:
            choice = int(input(f"{Fore.GREEN}请选择要使用的仓库编号: {Style.RESET_ALL}")) - 1
            if 0 <= choice < len(results):
                success = await backend.process_github_manifest(app_id, results[choice]['repo'], add_all_dlc, patch_depot_key)
                log.info(f"--- AppID {app_id} 处理 {'成功' if success else '失败'} ---\n")
            else: log.error("无效选择。")
        except (ValueError, EOFError, KeyboardInterrupt): log.error("无效输入或操作已取消。")

async def workshop_flow(backend: CaiBackend):
    log = backend.log
    log.info(f"\n{Fore.YELLOW}--- 创意工坊清单下载 ---{Style.RESET_ALL}")
    try:
        workshop_input_batch = input(f"{Fore.CYAN}{Back.BLACK}{Style.BRIGHT}请输入一个或多个创意工坊物品ID/URL (用英文逗号 ',' 分隔): {Style.RESET_ALL}").strip()
        if not workshop_input_batch:
            log.error("输入不能为空。"); return
        items_to_process = [item.strip() for item in workshop_input_batch.split(',') if item.strip()]
        for item in items_to_process:
            log.info(f"--- 开始处理: {item} ---")
            success = await backend.process_workshop_manifest(item)
            log.info(f"{Fore.GREEN if success else Fore.RED}--- '{item}' 处理{'成功' if success else '失败'} ---{Style.RESET_ALL}\n")
    except (EOFError, KeyboardInterrupt):
        log.warning("\n操作已取消。")

# --- MODIFIED: Simplified main async function, removed Steam environment checks ---
async def async_main():
    backend = CaiBackend()
    log = backend.log
    show_banner(backend)
    try:
        if not await backend.initialize():
            return
        await check_and_prompt_update(backend)

        if custom_repos := backend.get_custom_github_repos() + backend.get_custom_zip_repos():
            log.info(f"\n{Fore.GREEN}已检测到 {len(custom_repos)} 个自定义清单库配置。{Style.RESET_ALL}")

        while True:
            print(f"\n{Fore.YELLOW}请选择要执行的操作：")
            print(f"{Fore.CYAN}1. 下载游戏文件 (清单和LUA)")
            print(f"{Fore.CYAN}2. 下载创意工坊文件 (仅清单)")
            print(f"{Fore.CYAN}q. 退出程序{Style.RESET_ALL}")
            try:
                main_choice = input(f"{Fore.GREEN}请输入您的选择: {Style.RESET_ALL}").strip().lower()
                if main_choice == '1': await main_flow(backend)
                elif main_choice == '2': await workshop_flow(backend)
                elif main_choice in ['q', 'quit', 'exit']: break
                else: log.error("无效选择，请输入 1, 2 或 q。")
            except (EOFError, KeyboardInterrupt):
                log.warning("\n操作已取消，返回主菜单。")
    except Exception as e:
        log.error(f'主程序发生意外错误: {backend.stack_error(e)}')
    finally:
        await backend.cleanup_temp_files()
        await backend.close_resources()

def show_update_dialog_with_details(update_info: dict) -> str:
    root = tk.Tk()
    root.title("发现新版本")
    window_width, window_height = 600, 500
    pos_x = int(root.winfo_screenwidth() / 2 - window_width / 2)
    pos_y = int(root.winfo_screenheight() / 2 - window_height / 2)
    root.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
    root.resizable(False, False)

    latest_ver = update_info.get('latest_version', '未知')
    release_url = update_info.get('release_url', '')

    tk.Label(root, text="🎉 发现新版本可用！", font=("Arial", 16, "bold")).pack(pady=10)
    info_frame = tk.Frame(root); info_frame.pack(pady=10, padx=20, fill='x')
    tk.Label(info_frame, text=f"当前版本: {update_info.get('current_version', '未知')}", font=("Arial", 11)).pack(anchor='w')
    tk.Label(info_frame, text=f"最新版本: {latest_ver}", font=("Arial", 11, "bold"), fg="green").pack(anchor='w')
    
    tk.Label(root, text="更新内容:", font=("Arial", 11, "bold")).pack(anchor='w', padx=20, pady=(10, 5))
    text_frame = tk.Frame(root); text_frame.pack(padx=20, pady=5, fill='both', expand=True)
    text_widget = scrolledtext.ScrolledText(text_frame, wrap='word', height=10); text_widget.pack(fill='both', expand=True)
    text_widget.insert('1.0', update_info.get('release_body', '暂无更新日志')); text_widget.config(state='disabled')

    user_choice = {'action': 'skip'}
    button_frame = tk.Frame(root); button_frame.pack(pady=20)
    def on_action(action):
        user_choice['action'] = action
        if action == 'update' and release_url: webbrowser.open(release_url)
        if action == 'ignore':
            try:
                settings_path = Path('./update_settings.json')
                settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
                settings['ignored_version'] = latest_ver
                settings_path.write_text(json.dumps(settings, indent=2), encoding='utf-8')
            except Exception as e: print(f"保存忽略版本失败: {e}")
        root.destroy()

    tk.Button(button_frame, text="立即更新", command=lambda: on_action('update'), bg="green", fg="white", font=("Arial", 11, "bold"), width=12, height=2).pack(side='left', padx=5)
    tk.Button(button_frame, text="稍后提醒", command=lambda: on_action('skip'), font=("Arial", 10), width=10).pack(side='left', padx=5)
    tk.Button(button_frame, text="忽略此版本", command=lambda: on_action('ignore'), font=("Arial", 10), width=10).pack(side='left', padx=5)
    root.focus_force()
    root.mainloop()
    return user_choice['action']

async def check_and_prompt_update(backend: CaiBackend):
    try:
        settings_path = Path('./update_settings.json')
        ignored_version = ''
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding='utf-8'))
                if settings.get('disable_update_check', False):
                    backend.log.info("自动更新检查已禁用"); return
                ignored_version = settings.get('ignored_version', '')
            except Exception: pass
        has_update, update_info = await backend.check_for_updates()
        if has_update and ignored_version != update_info.get('latest_version', ''):
            action = show_update_dialog_with_details(update_info)
            if action == 'update': backend.log.info("用户选择更新，正在打开下载页面...")
            elif action == 'ignore': backend.log.info(f"用户选择忽略版本 {update_info.get('latest_version', '')}")
            else: backend.log.info("用户选择稍后更新")
    except Exception as e:
        backend.log.warning(f"更新检查过程出错: {e}")

if __name__ == '__main__':
    show_info_dialog()
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n用户中断了程序。")
    finally:
        print("\n操作完成。按任意键退出...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass