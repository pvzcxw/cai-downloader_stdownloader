# --- START OF FILE backend.py ---

import sys
import os
import traceback
import time
import logging
import subprocess
import asyncio
import random
import string
import re
import aiofiles
import colorlog
import httpx
import winreg
import ujson as json
import vdf
import zipfile
import shutil
import struct
import zlib
import io
from pathlib import Path
from typing import Tuple, Any, List, Dict, Literal

CURRENT_VERSION = "1.4"  # 当前版本号
GITHUB_REPO = "pvzcxw/cai-downloader_stdownloader" 

# --- LOGGING SETUP ---
LOG_FORMAT = '%(log_color)s%(message)s'
LOG_COLORS = {
    'INFO': 'cyan',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'purple',
}

# --- DEFAULT CONFIG ---
DEFAULT_CONFIG = {
    "Github_Personal_Token": "",
    "Custom_Repos": {
        "github": [],
        "zip": []
    },
    "QA1": "温馨提示: Github_Personal_Token(个人访问令牌)可在Github设置的最底下开发者选项中找到, 详情请看教程。",
    "QA2": "Custom_Repos: 自定义清单库配置。github数组用于添加GitHub仓库，zip数组用于添加ZIP清单库。",
    "QA3": "GitHub仓库格式: {\"name\": \"显示名称\", \"repo\": \"用户名/仓库名\"}",
    "QA4": "ZIP清单库格式: {\"name\": \"显示名称\", \"url\": \"下载URL，用{app_id}作为占位符\"}"
}

class STConverter:
    def __init__(self):
        self.logger = logging.getLogger('STConverter')

    def convert_file(self, st_path: str) -> str:
        try:
            content, _ = self.parse_st_file(st_path)
            return content
        except Exception as e:
            self.logger.error(f'ST文件转换失败: {st_path} - {e}')
            raise

    def parse_st_file(self, st_file_path: str) -> Tuple[str, dict]:
        with open(st_file_path, 'rb') as stfile:
            content = stfile.read()
        if len(content) < 12: raise ValueError("文件头过短")
        header = content[:12]
        xorkey, size, xorkeyverify = struct.unpack('III', header)
        xorkey ^= 0xFFFEA4C8
        xorkey &= 0xFF
        encrypted_data = content[12:12+size]
        if len(encrypted_data) < size: raise ValueError("加密数据小于预期大小")
        data = bytearray(encrypted_data)
        for i in range(len(data)):
            data[i] ^= xorkey
        decompressed_data = zlib.decompress(data)
        lua_content = decompressed_data[512:].decode('utf-8')
        metadata = {'original_xorkey': xorkey, 'size': size, 'xorkeyverify': xorkeyverify}
        return lua_content, metadata

class CaiBackend:
    def __init__(self):
        self.client = httpx.AsyncClient(verify=False, trust_env=True, timeout=30)
        self.config = {}
        # --- MODIFIED: Removed Steam-specific properties ---
        self.unlocker_type = "downloader" # Set static type for downloader mode
        self.lock = asyncio.Lock()
        self.temp_path = Path('./temp')
        self.log = self._init_log()

    def _init_log(self, level=logging.DEBUG) -> logging.Logger:
        logger = logging.getLogger(' Cai Downloader')
        logger.setLevel(level)
        if not logger.handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(level)
            fmt = colorlog.ColoredFormatter(LOG_FORMAT, log_colors=LOG_COLORS)
            stream_handler.setFormatter(fmt)
            logger.addHandler(stream_handler)
        return logger
    
    # --- NEW: Helper function to get the local output path for an AppID ---
    def get_output_path_for_app(self, app_id: str) -> Path:
        """Creates and returns the output directory for a specific AppID."""
        output_path = Path(f'./cai_downloads/{app_id}')
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _compare_versions(self, v1: str, v2: str) -> int:
        try:
            import re
            
            def parse_version(v):
                match = re.match(r'(\d+(?:\.\d+)*)(.*)', v)
                if not match: return (0, 0, 0), ''
                version_nums = match.group(1)
                suffix = match.group(2)
                parts = version_nums.split('.')
                while len(parts) < 3: parts.append('0')
                version_tuple = tuple(int(p) for p in parts[:3])
                return version_tuple, suffix
            
            v1_tuple, v1_suffix = parse_version(v1)
            v2_tuple, v2_suffix = parse_version(v2)
            
            if v1_tuple < v2_tuple: return -1
            elif v1_tuple > v2_tuple: return 1
            
            if not v1_suffix and v2_suffix: return 1
            elif v1_suffix and not v2_suffix: return -1
            elif v1_suffix < v2_suffix: return -1
            elif v1_suffix > v2_suffix: return 1
            
            return 0
            
        except Exception as e:
            self.log.warning(f"版本比较失败: {e}")
            return 0
    
    async def download_update(self, download_url: str, save_path: Path) -> bool:
        try:
            self.log.info(f"开始下载更新: {download_url}")
            save_path.parent.mkdir(parents=True, exist_ok=True)
            response = await self.client.get(download_url, follow_redirects=True, timeout=300)
            response.raise_for_status()
            async with aiofiles.open(save_path, 'wb') as f:
                await f.write(response.content)
            self.log.info(f"更新下载完成: {save_path}")
            return True
        except Exception as e:
            self.log.error(f"下载更新失败: {e}")
            return False
        
    async def check_for_updates(self) -> Tuple[bool, Dict]:
        try:
            self.log.info("正在检查更新...")
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            github_token = self.config.get("Github_Personal_Token", "").strip()
            headers = {'Authorization': f'Bearer {github_token}'} if github_token else {}
            headers['User-Agent'] = 'Cai-Install-Updater'
            response = await self.client.get(api_url, headers=headers, timeout=10)
            if response.status_code == 404:
                self.log.info("未找到发布版本")
                return False, {}
            response.raise_for_status()
            release_data = response.json()
            latest_version = release_data.get('tag_name', '').strip().lstrip('v')
            
            download_urls = []
            for asset in release_data.get('assets', []):
                download_urls.append({
                    'name': asset.get('name', ''),
                    'url': asset.get('browser_download_url', ''),
                    'size': asset.get('size', 0)
                })
            
            if not download_urls and release_data.get('zipball_url'):
                download_urls.append({
                    'name': 'Source code (zip)',
                    'url': release_data.get('zipball_url', ''),
                    'size': 0
                })
            
            if self._compare_versions(CURRENT_VERSION.split('-')[0], latest_version) < 0:
                self.log.info(f"发现新版本: {latest_version} (当前版本: {CURRENT_VERSION})")
                return True, {
                    'current_version': CURRENT_VERSION,
                    'latest_version': latest_version,
                    'release_name': release_data.get('name', ''),
                    'release_body': release_data.get('body', ''),
                    'release_url': release_data.get('html_url', ''),
                    'published_at': release_data.get('published_at', ''),
                    'download_urls': download_urls
                }
            else:
                self.log.info(f"当前已是最新版本 ({CURRENT_VERSION})")
                return False, {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403: self.log.warning("GitHub API 请求次数已用尽，跳过更新检查")
            else: self.log.warning(f"检查更新时 HTTP 错误: {e}")
            return False, {}
        except Exception as e:
            self.log.warning(f"检查更新失败: {e}")
            return False, {}

    # --- MODIFIED: Simplified initialization, removed all Steam path and unlocker detection ---
    async def initialize(self) -> bool:
        """Initializes the backend by loading the configuration."""
        self.config = await self.load_config()
        if self.config is None:
            self.log.error("无法加载配置。正在退出。")
            return False
        
        self.log.info("Cai Downloader 初始化成功。")
        return True

    async def close_resources(self):
        await self.client.aclose()

    def stack_error(self, exception: Exception) -> str:
        return ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))

    async def gen_config_file(self):
        try:
            async with aiofiles.open("./config.json", mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))
            self.log.info('未识别到config.json，可能为首次启动，已自动生成，若进行配置重启生效')
        except Exception as e:
            self.log.error(f'生成配置文件失败: {self.stack_error(e)}')

    async def load_config(self) -> Dict | None:
        if not os.path.exists('./config.json'):
            await self.gen_config_file()
            return DEFAULT_CONFIG
        try:
            async with aiofiles.open("./config.json", mode="r", encoding="utf-8") as f:
                user_config = json.loads(await f.read())
                config = DEFAULT_CONFIG.copy()
                config.update(user_config)
                if 'Custom_Repos' not in config:
                    config['Custom_Repos'] = {"github": [], "zip": []}
                elif not isinstance(config['Custom_Repos'], dict):
                    config['Custom_Repos'] = {"github": [], "zip": []}
                else:
                    if 'github' not in config['Custom_Repos']: config['Custom_Repos']['github'] = []
                    if 'zip' not in config['Custom_Repos']: config['Custom_Repos']['zip'] = []
                return config
        except Exception as e:
            self.log.error(f"加载配置文件失败: {self.stack_error(e)}。正在重置配置文件...")
            if os.path.exists("./config.json"): os.remove("./config.json")
            await self.gen_config_file()
            self.log.error("配置文件已损坏并被重置。请重启程序。")
            return None

    def get_custom_github_repos(self) -> List[Dict]:
        custom_repos = self.config.get("Custom_Repos", {}).get("github", [])
        validated_repos = []
        for repo in custom_repos:
            if isinstance(repo, dict) and 'name' in repo and 'repo' in repo:
                validated_repos.append(repo)
            else:
                self.log.warning(f"无效的自定义GitHub仓库配置: {repo}")
        return validated_repos

    def get_custom_zip_repos(self) -> List[Dict]:
        custom_repos = self.config.get("Custom_Repos", {}).get("zip", [])
        validated_repos = []
        for repo in custom_repos:
            if isinstance(repo, dict) and 'name' in repo and 'url' in repo and '{app_id}' in repo['url']:
                validated_repos.append(repo)
            else:
                self.log.warning(f"无效的自定义ZIP仓库配置或缺少{{app_id}}占位符: {repo}")
        return validated_repos

    async def process_custom_zip_manifest(self, app_id: str, repo_config: Dict, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        repo_name = repo_config.get('name', '未知仓库')
        url_template = repo_config.get('url', '')
        download_url = url_template.replace('{app_id}', app_id)
        return await self._process_zip_manifest_generic(app_id, download_url, f"自定义ZIP库 ({repo_name})", add_all_dlc, patch_depot_key)

    def get_all_github_repos(self) -> List[str]:
        builtin_repos = ['Auiowu/ManifestAutoUpdate', 'SteamAutoCracks/ManifestHub']
        custom_repos = [repo['repo'] for repo in self.get_custom_github_repos()]
        return builtin_repos + custom_repos

    async def download_depotkeys_json(self) -> Dict | None:
        try:
            self.log.info("正在从 SteamAutoCracks 仓库下载 depotkeys.json...")
            urls = ["https://raw.githubusercontent.com/SteamAutoCracks/ManifestHub/main/depotkeys.json"]
            if os.environ.get('IS_CN') == 'yes':
                urls = [
                    "https://cdn.jsdmirror.com/gh/SteamAutoCracks/ManifestHub@main/depotkeys.json",
                    "https://raw.gitmirror.com/SteamAutoCracks/ManifestHub/main/depotkeys.json", 
                    "https://raw.dgithub.xyz/SteamAutoCracks/ManifestHub/main/depotkeys.json",
                    "https://gh.akass.cn/SteamAutoCracks/ManifestHub/main/depotkeys.json",
                    "https://raw.githubusercontent.com/SteamAutoCracks/ManifestHub/main/depotkeys.json"
                ]
            for attempt, url in enumerate(urls, 1):
                try:
                    self.log.info(f"尝试从源 {attempt}/{len(urls)} 下载: {url.split('/')[2]}")
                    for retry in range(2):
                        try:
                            response = await self.client.get(url, timeout=15)
                            response.raise_for_status()
                            depotkeys_data = response.json()
                            self.log.info(f"成功下载 depotkeys.json，包含 {len(depotkeys_data)} 个条目。(来源: {url.split('/')[2]})")
                            return depotkeys_data
                        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
                            if retry == 0:
                                self.log.warning(f"连接超时，正在重试... (源: {url.split('/')[2]})")
                                await asyncio.sleep(1)
                            else:
                                raise
                except Exception as e:
                    self.log.warning(f"源 {url.split('/')[2]} 下载失败: {e}")
                    if attempt == len(urls): raise Exception("所有镜像源均不可用")
            raise Exception("所有镜像源均不可用")
        except Exception as e:
            self.log.error(f"下载 depotkeys.json 失败: {self.stack_error(e)}")
            return None

    async def patch_lua_with_depotkey(self, app_id: str, lua_file_path: Path) -> bool:
        try:
            if 'IS_CN' not in os.environ:
                self.log.info("检测网络环境以优化下载源选择...")
                await self.checkcn()
            depotkeys_data = await self.download_depotkeys_json()
            if not depotkeys_data:
                self.log.error("无法获取 depotkeys 数据，跳过 depotkey 修补。")
                return False
            if app_id not in depotkeys_data:
                self.log.warning(f"没有此AppID的depotkey: {app_id}")
                return False
            depotkey = depotkeys_data[app_id]
            if not depotkey or not str(depotkey).strip():
                self.log.warning(f"AppID {app_id} 的 depotkey 为空或无效，跳过修补: '{depotkey}'")
                return False
            depotkey = str(depotkey).strip()
            self.log.info(f"找到 AppID {app_id} 的有效 depotkey: {depotkey}")
            if not lua_file_path.exists():
                self.log.error(f"LUA文件不存在: {lua_file_path}")
                return False
            async with aiofiles.open(lua_file_path, 'r', encoding='utf-8') as f:
                lua_content = await f.read()
            lines = lua_content.strip().split('\n')
            new_lines = []
            app_id_line_removed = False
            for line in lines:
                line = line.strip()
                if line == f"addappid({app_id})":
                    new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                    app_id_line_removed = True
                    self.log.info(f"已替换: addappid({app_id}) -> addappid({app_id},1,\"{depotkey}\")")
                else:
                    new_lines.append(line)
            if not app_id_line_removed:
                new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                self.log.info(f"已添加新的 depotkey 条目: addappid({app_id},1,\"{depotkey}\")")
            async with aiofiles.open(lua_file_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(new_lines) + '\n')
            self.log.info(f"成功修补 LUA 文件的 depotkey: {lua_file_path.name}")
            return True
        except Exception as e:
            self.log.error(f"修补 LUA depotkey 时出错: {self.stack_error(e)}")
            return False

    async def _get_buqiuren_session_token(self) -> str | None:
        backup_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://manifest.steam.run/", "Origin": "https://manifest.steam.run"}
            session_resp = await self.client.post("https://manifest.steam.run/api/session", headers=headers, timeout=30)
            if session_resp.status_code == 200:
                token = session_resp.json().get("token")
                if token:
                    self.log.info(f"成功获取不求人会话令牌: ...{token[-6:]}")
                    return token
            self.log.warning("使用备用令牌")
        except Exception as e:
            self.log.warning(f"获取不求人会话令牌时出错: {e}")
        return backup_token

    # --- MODIFIED: Added app_id to save file to correct local directory ---
    async def _download_manifest_buqiuren(self, app_id: str, depot_id: str, manifest_id: str, depot_name: str) -> bool:
        output_filename = f"{depot_id}_{manifest_id}.manifest"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session_token = await self._get_buqiuren_session_token()
                if not session_token:
                    if attempt < max_retries - 1: await asyncio.sleep(5); continue
                    return False
                self.log.info(f"正在请求清单下载链接... [Depot: {depot_id}, Manifest: {manifest_id}]")
                payload = {"depot_id": str(depot_id), "manifest_id": str(manifest_id), "token": session_token}
                headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://manifest.steam.run/", "Origin": "https://manifest.steam.run", "Content-Type": "application/json"}
                await asyncio.sleep(random.uniform(2, 5))
                code_response = await self.client.post("https://manifest.steam.run/api/request-code", json=payload, headers=headers, timeout=60)
                if code_response.status_code == 429:
                    self.log.warning(f"请求频率过高，等待后重试...")
                    if attempt < max_retries - 1: await asyncio.sleep(30); continue
                    return False
                if code_response.status_code != 200:
                    self.log.error(f"请求失败，状态码: {code_response.status_code}")
                    if attempt < max_retries - 1: await asyncio.sleep(10); continue
                    return False
                code_data = code_response.json()
                download_url = code_data.get("download_url")
                if not download_url:
                    error_msg = code_data.get('error', code_data.get('message', '未知错误'))
                    self.log.error(f"请求下载链接失败: {error_msg}")
                    if attempt < max_retries - 1: await asyncio.sleep(15); continue
                    return False
                self.log.info(f"获取到下载链接，正在下载清单文件...")
                manifest_response = await self.client.get(download_url, timeout=180)
                if manifest_response.status_code != 200:
                    self.log.error(f"下载失败，状态码: {manifest_response.status_code}")
                    if attempt < max_retries - 1: continue
                    return False
                manifest_content = manifest_response.content
                final_content = manifest_content
                if manifest_content.startswith(b'PK\x03\x04'):
                    self.log.info("检测到ZIP文件，正在自动解压...")
                    try:
                        with io.BytesIO(manifest_content) as mem_zip, zipfile.ZipFile(mem_zip, 'r') as z:
                            file_list = z.namelist()
                            if len(file_list) == 1:
                                final_content = z.read(file_list[0])
                    except Exception as e:
                        self.log.warning(f"处理ZIP文件时出错: {e}")
                
                if not final_content:
                    if attempt < max_retries - 1: continue
                    return False
                
                # --- MODIFIED: Save to local download directory ---
                output_path = self.get_output_path_for_app(app_id)
                (output_path / output_filename).write_bytes(final_content)
                self.log.info(f"清单已保存到: {output_path / output_filename}")
                self.log.info(f"成功下载清单: {depot_name} ({output_filename})")
                return True
            except Exception as e:
                self.log.error(f"下载过程中出错: {e}")
                if attempt < max_retries - 1:
                    self.log.info(f"等待后重试... (尝试 {attempt + 2}/{max_retries})")
                    await asyncio.sleep(15)
        self.log.error(f"下载清单 {output_filename} 失败：所有重试都失败了")
        return False

    async def process_buqiuren_manifest(self, app_id: str) -> bool:
        try:
            self.log.info(f'正从 清单不求人库 处理 AppID {app_id} 的清单...')
            depot_manifest_map = await self._get_depots_and_manifests_from_steamui(app_id)
            if not depot_manifest_map:
                self.log.error(f"未能从 steamui API 获取到 AppID {app_id} 的 depot 信息")
                return False
            self.log.info(f"从 steamui API 获取到 {len(depot_manifest_map)} 个 depot 及其 manifest")
            success_count, total_count = 0, len(depot_manifest_map)
            for i, (depot_id, manifest_id) in enumerate(depot_manifest_map.items(), 1):
                self.log.info(f"处理进度: {i}/{total_count}")
                # --- MODIFIED: Pass app_id to the download function ---
                if await self._download_manifest_buqiuren(app_id, depot_id, manifest_id, f"Depot {depot_id}"):
                    success_count += 1
                else:
                    self.log.warning(f"下载 depot {depot_id} 的清单失败")
                if i < total_count:
                    delay = random.uniform(10, 20)
                    self.log.info(f"等待 {delay:.1f} 秒后继续...")
                    await asyncio.sleep(delay)
            if success_count == 0:
                self.log.error(f"AppID {app_id} 没有成功下载任何清单")
                return False
            self.log.info(f"成功处理不求人库清单: 成功 {success_count}/{total_count}")
            return True
        except Exception as e:
            self.log.error(f'处理不求人库清单时出错: {self.stack_error(e)}')
            return False

    def _extract_workshop_id(self, input_text: str) -> str | None:
        input_text = input_text.strip()
        if not input_text: return None
        url_match = re.search(r"https?://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)", input_text)
        if url_match: return url_match.group(1)
        if input_text.isdigit(): return input_text
        return None

    async def _get_workshop_details(self, workshop_id: str) -> Tuple[str, str, str] | None:
        self.log.info(f"正在查询创意工坊物品 {workshop_id} 的信息...")
        api_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
        data = {'itemcount': 1, 'publishedfileids[0]': workshop_id}
        max_retries, retry_delay = 3, 2
        for attempt in range(max_retries):
            try:
                response = await self.client.post(api_url, data=data)
                response.raise_for_status()
                result = response.json()
                if 'response' not in result or 'publishedfiledetails' not in result['response'] or not result['response']['publishedfiledetails']:
                    self.log.error("API响应格式不正确或未找到物品详情")
                    return None
                details = result['response']['publishedfiledetails'][0]
                if int(details.get('result', 0)) != 1:
                    self.log.error(f"未找到创意工坊物品: {workshop_id}")
                    return None
                consumer_app_id = details.get('consumer_app_id')
                hcontent_file = details.get('hcontent_file')
                title = details.get('title', '未知标题')
                if not consumer_app_id or not hcontent_file:
                    self.log.error(f"创意工坊物品 '{title}' 缺少必要的信息 (App ID 或 Manifest ID)。")
                    return None
                self.log.info(f"成功获取创意工坊物品信息:\n  标题: {title}\n  所属游戏 AppID: {consumer_app_id}\n  清单 ManifestID: {hcontent_file}")
                return str(consumer_app_id), str(hcontent_file), title
            except Exception as e:
                self.log.error(f"获取创意工坊物品信息出错: {self.stack_error(e)}")
                if attempt < max_retries - 1: await asyncio.sleep(retry_delay)
        return None

    # --- MODIFIED: Added app_id to save file to correct local directory ---
    async def _download_and_place_workshop_manifest(self, app_id: str, depot_id: str, manifest_id: str) -> bool:
        output_filename = f"{depot_id}_{manifest_id}.manifest"
        self.log.info(f"准备下载清单: {output_filename}")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session_token = await self._get_session_token()
                if not session_token:
                    if attempt < max_retries - 1: await asyncio.sleep(5); continue
                    return False
                self.log.info(f"正在请求清单下载链接... [Depot: {depot_id}, Manifest: {manifest_id}]")
                payload = {"depot_id": str(depot_id), "manifest_id": str(manifest_id), "token": session_token}
                headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://manifest.steam.run/", "Origin": "https://manifest.steam.run", "Content-Type": "application/json"}
                await asyncio.sleep(2)
                code_response = await self.client.post("https://manifest.steam.run/api/request-code", json=payload, headers=headers, timeout=60)
                if code_response.status_code == 429:
                    self.log.warning(f"请求频率过高，等待后重试...")
                    if attempt < max_retries - 1: await asyncio.sleep(30); continue
                    return False
                if code_response.status_code != 200:
                    self.log.error(f"请求失败，状态码: {code_response.status_code}")
                    if attempt < max_retries - 1: await asyncio.sleep(10); continue
                    return False
                code_data = code_response.json()
                download_url = code_data.get("download_url")
                if not download_url:
                    error_msg = code_data.get('error', code_data.get('message', '未知错误'))
                    self.log.error(f"请求下载链接失败: {error_msg}")
                    if attempt < max_retries - 1: await asyncio.sleep(15); continue
                    return False
                self.log.info(f"获取到下载链接，正在下载清单文件...")
                manifest_response = await self.client.get(download_url, timeout=180)
                if manifest_response.status_code != 200:
                    self.log.error(f"下载失败，状态码: {manifest_response.status_code}")
                    if attempt < max_retries - 1: continue
                    return False
                manifest_content = manifest_response.content
                final_content = manifest_content
                if manifest_content.startswith(b'PK\x03\x04'):
                    self.log.info("检测到ZIP文件，正在自动解压...")
                    try:
                        with io.BytesIO(manifest_content) as mem_zip, zipfile.ZipFile(mem_zip, 'r') as z:
                            file_list = z.namelist()
                            if len(file_list) == 1: final_content = z.read(file_list[0])
                    except Exception as e:
                        self.log.warning(f"处理ZIP文件时出错: {e}")
                
                if not final_content:
                    if attempt < max_retries - 1: continue
                    return False
                
                # --- MODIFIED: Save to local download directory ---
                output_path = self.get_output_path_for_app(app_id)
                (output_path / output_filename).write_bytes(final_content)
                self.log.info(f"清单已保存到: {output_path / output_filename}")
                self.log.info(f"成功处理创意工坊清单 {output_filename}。")
                return True
            except Exception as e:
                self.log.error(f"下载过程中出错: {e}")
                if attempt < max_retries - 1:
                    self.log.info(f"等待后重试... (尝试 {attempt + 2}/{max_retries})")
                    await asyncio.sleep(15)
        self.log.error(f"下载清单 {output_filename} 失败：所有重试都失败了")
        return False
    
    async def _get_session_token(self) -> str | None:
        backup_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        try:
            self.log.info("正在获取会话令牌...")
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://manifest.steam.run/", "Origin": "https://manifest.steam.run"}
            session_resp = await self.client.post("https://manifest.steam.run/api/session", headers=headers, timeout=30)
            if session_resp.status_code == 200:
                token = session_resp.json().get("token")
                if token:
                    self.log.info(f"成功获取会话令牌: ...{token[-6:]}")
                    return token
            self.log.warning("会话令牌获取失败，使用备用令牌")
        except Exception as e:
            self.log.warning(f"获取会话令牌时出错: {e}，使用备用令牌")
        return backup_token

    async def process_workshop_manifest(self, workshop_input: str) -> bool:
        workshop_id = self._extract_workshop_id(workshop_input)
        if not workshop_id:
            self.log.error(f"无效的创意工坊物品ID或URL: '{workshop_input}'")
            return False
        details = await self._get_workshop_details(workshop_id)
        if not details:
            return False
        consumer_app_id, hcontent_file, _ = details
        # --- MODIFIED: Pass consumer_app_id to the download function ---
        return await self._download_and_place_workshop_manifest(consumer_app_id, consumer_app_id, hcontent_file)
    
    async def check_github_api_rate_limit(self) -> bool:
        github_token = self.config.get("Github_Personal_Token", "").strip()
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        if github_token: self.log.info("已配置GitHub Token。")
        else: self.log.warning("未找到GitHub Token。您的API请求将受到严格的速率限制。")
        try:
            r = await self.client.get('https://api.github.com/rate_limit', headers=headers)
            r.raise_for_status()
            rate_limit = r.json().get('resources', {}).get('core', {})
            remaining = rate_limit.get('remaining', 0)
            self.log.info(f'GitHub API剩余请求次数: {remaining}')
            if remaining == 0:
                self.log.error("GitHub API请求次数已用尽。")
                return False
            return True
        except Exception as e:
            self.log.error(f'检查GitHub API速率限制失败: {self.stack_error(e)}')
            return False

    async def checkcn(self) -> bool:
        try:
            req = await self.client.get('https://mips.kugou.com/check/iscn?&format=json', timeout=5)
            body = req.json()
            is_cn = bool(body['flag'])
            os.environ['IS_CN'] = 'yes' if is_cn else 'no'
            self.log.info(f"检测到区域为 {'中国大陆' if is_cn else '非中国大陆'} ({body['country']})。")
            return is_cn
        except Exception:
            os.environ['IS_CN'] = 'yes'
            self.log.warning('无法确定服务器位置，默认您在中国大陆。')
            return True

    def parse_lua_file_for_depots(self, lua_file_path: str) -> Dict:
        addappid_pattern = re.compile(r'addappid\((\d+),\s*1,\s*"([^"]+)"\)')
        depots = {}
        try:
            with open(lua_file_path, 'r', encoding='utf-8') as file:
                lua_content = file.read()
                for match in addappid_pattern.finditer(lua_content):
                    depots[match.group(1)] = {"DecryptionKey": match.group(2)}
        except Exception as e:
            self.log.error(f"解析lua文件 {lua_file_path} 出错: {e}")
        return depots

    async def _get_from_mirrors(self, sha: str, path: str, repo: str) -> bytes:
        urls = [f'https://raw.githubusercontent.com/{repo}/{sha}/{path}']
        if os.environ.get('IS_CN') == 'yes':
            urls = [
                f'https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}',
                f'https://raw.gitmirror.com/{repo}/{sha}/{path}',
                f'https://raw.dgithub.xyz/{repo}/{sha}/{path}',
                f'https://gh.akass.cn/{repo}/{sha}/{path}'
            ] + urls
        for url in urls:
            try:
                r = await self.client.get(url, timeout=30)
                if r.status_code == 200:
                    self.log.info(f'下载成功: {path} (来自 {url.split("/")[2]})')
                    return r.content
                self.log.error(f'下载失败: {path} (来自 {url.split("/")[2]}) - 状态码: {r.status_code}')
            except httpx.RequestError as e:
                self.log.error(f'下载失败: {path} (来自 {url.split("/")[2]}) - 错误: {e}')
        raise Exception(f'尝试所有镜像后仍无法下载文件: {path}')

    async def _http_get_safe(self, url: str) -> httpx.Response | None:
        try:
            response = await self.client.get(url, timeout=20)
            response.raise_for_status()
            return response
        except Exception as e:
            self.log.error(f"HTTP请求失败 {url}: {e}")
            return None

    async def _get_dlc_ids_safe(self, appid: str) -> List[str]:
        """
        获取DLC列表，优先级: ddxnb -> steamcmd -> steam store
        """
        
        # 定义通用的 SteamCMD 格式解析函数，避免代码重复
        def parse_steamcmd_style_json(json_data: dict) -> List[str]:
            try:
                info = json_data.get("data", {}).get(str(appid), {})
                dlc_str = info.get("extended", {}).get("listofdlc", "")
                if dlc_str:
                    return sorted(filter(str.isdigit, map(str.strip, dlc_str.split(","))), key=int)
            except Exception:
                pass
            return []

        # --- 优先级 1: ddxnb 源 ---
        self.log.info(f"正在尝试从 ddxnb源 获取 AppID {appid} 的DLC列表...")
        data = await self._http_get_safe(f"https://steam.ddxnb.cn/v1/info/{appid}")
        if data:
            try:
                dlc_ids = parse_steamcmd_style_json(data.json())
                if dlc_ids:
                    self.log.info(f"从 ddxnb源 获取到 {len(dlc_ids)} 个DLC")
                    return dlc_ids
            except Exception as e:
                self.log.warning(f"解析 ddxnb源 响应失败: {e}")
        else:
            self.log.info("ddxnb源无响应或请求失败，尝试下一节点...")

        # --- 优先级 2: SteamCMD 源 ---
        self.log.info(f"正在尝试从 SteamCMD源 获取 AppID {appid} 的DLC列表...")
        data = await self._http_get_safe(f"https://api.steamcmd.net/v1/info/{appid}")
        if data:
            try:
                dlc_ids = parse_steamcmd_style_json(data.json())
                if dlc_ids:
                    self.log.info(f"从 SteamCMD API 获取到 {len(dlc_ids)} 个DLC")
                    return dlc_ids
            except Exception as e:
                self.log.warning(f"解析 SteamCMD API 响应失败: {e}")
        else:
            self.log.info("SteamCMD源无响应或请求失败，尝试下一节点...")

        # --- 优先级 3: Steam Store 官方源 ---
        self.log.info(f"正在尝试从 Steam Store源 获取 AppID {appid} 的DLC列表...")
        data = await self._http_get_safe(f"https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese")
        if data:
            try:
                j = data.json()
                if j.get(str(appid), {}).get("success") and "data" in j[str(appid)]:
                    dlc_ids = [str(d) for d in j[str(appid)]["data"].get("dlc", [])]
                    if dlc_ids:
                        self.log.info(f"从 Steam Store API 获取到 {len(dlc_ids)} 个DLC")
                        return dlc_ids
            except Exception as e:
                self.log.warning(f"解析 Steam Store API 响应失败: {e}")
        
        self.log.warning(f"未能从任何API (ddxnb, SteamCMD, Steam Store) 获取到 AppID {appid} 的DLC信息")
        return []

    async def _get_depots_safe(self, appid: str) -> List[Dict]:
        """
        获取Depot信息，优先级: ddxnb -> steamcmd
        注意：Steam Store API 不提供详细的 Depot 结构信息，所以没有第三步兜底
        """
        
        # 定义通用的解析函数，因为 ddxnb 和 steamcmd 返回结构一致
        def parse_depots_from_json(json_data: dict) -> List[Dict]:
            try:
                info = json_data.get("data", {}).get(str(appid), {})
                depots_raw = info.get("depots", {})
                out = []
                if depots_raw:
                    for depot_id, depot_info in depots_raw.items():
                        if isinstance(depot_info, dict):
                           out.append({"depot_id": depot_id, "dlc_appid": depot_info.get("dlcappid")})
                return out
            except Exception:
                return []

        # --- 优先级 1: ddxnb 源 ---
        # self.log.debug(f"正在尝试从 ddxnb源 获取 AppID {appid} 的Depot信息...") 
        data = await self._http_get_safe(f"https://steam.ddxnb.cn/v1/info/{appid}")
        if data:
            try:
                out = parse_depots_from_json(data.json())
                if out:
                    # self.log.info(f"从 ddxnb源 获取到 {len(out)} 个Depot (AppID: {appid})")
                    return out
                # 如果返回了数据但是没有 depot，可能是空数据，但也算成功获取
                if "data" in data.json(): 
                    return [] 
            except Exception as e:
                self.log.warning(f"解析 ddxnb源 Depot信息失败: {e}")
        
        # --- 优先级 2: SteamCMD 源 ---
        # 只有当 ddxnb 失败（网络错误或解析严重错误）时才走这里
        # self.log.info(f"ddxnb失败，正在尝试从 SteamCMD源 获取 AppID {appid} 的Depot信息...")
        data = await self._http_get_safe(f"https://api.steamcmd.net/v1/info/{appid}")
        if data:
            try:
                out = parse_depots_from_json(data.json())
                if out:
                    # self.log.info(f"从 SteamCMD API 获取到 {len(out)} 个Depot (AppID: {appid})")
                    return out
                if "data" in data.json():
                    return []
            except Exception as e:
                self.log.warning(f"解析 SteamCMD API Depot 信息失败: {e}")

        # 如果都失败了
        # self.log.warning(f"未能从任何API获取到 AppID {appid} 的Depot信息")
        return []

    async def _get_dlc_ids(self, appid: str) -> List[str]:
        return await self._get_dlc_ids_safe(appid)

    async def _get_depots(self, appid: str) -> List[Dict]:
        return await self._get_depots_safe(appid)

    async def _add_free_dlcs_to_lua(self, app_id: str, lua_filepath: Path):
        self.log.info(f"开始为 AppID {app_id} 查找无密钥/无Depot的DLC...")
        try:
            all_dlc_ids = await self._get_dlc_ids(app_id)
            if not all_dlc_ids:
                self.log.info(f"AppID {app_id} 未找到任何DLC。")
                return
            tasks = [self._get_depots(dlc_id) for dlc_id in all_dlc_ids]
            results = await asyncio.gather(*tasks)
            depot_less_dlc_ids = [dlc_id for dlc_id, dlc_depots in zip(all_dlc_ids, results) if not dlc_depots]
            if not depot_less_dlc_ids:
                self.log.info(f"未找到适用于 AppID {app_id} 的无密钥/无Depot的DLC。")
                return
            async with self.lock:
                if not lua_filepath.exists():
                    self.log.error(f"目标LUA文件 {lua_filepath} 不存在，无法合并DLC。")
                    return
                async with aiofiles.open(lua_filepath, 'r', encoding='utf-8') as f:
                    existing_lines = [line.strip() for line in await f.readlines() if line.strip()]
                existing_appids = {match.group(1) for line in existing_lines if (match := re.search(r'addappid\((\d+)', line))}
                new_dlcs_to_add = [dlc_id for dlc_id in depot_less_dlc_ids if dlc_id not in existing_appids]
                if not new_dlcs_to_add:
                    self.log.info(f"所有找到的无Depot DLC均已存在于解锁文件中。无需添加。")
                    return
                self.log.info(f"找到 {len(new_dlcs_to_add)} 个新的无密钥/无Depot DLC，正在合并到 LUA 文件...")
                final_lines = set(existing_lines)
                for dlc_id in new_dlcs_to_add: final_lines.add(f"addappid({dlc_id})")
                def sort_key(line):
                    if (m := re.search(r'addappid\((\d+)', line)): return (0, int(m.group(1)))
                    if (m := re.search(r'setManifestid\((\d+)', line)): return (1, int(m.group(1)))
                    return (2, line)
                sorted_lines = sorted(list(final_lines), key=sort_key)
                async with aiofiles.open(lua_filepath, 'w', encoding='utf-8') as f:
                    await f.write('\n'.join(sorted_lines) + '\n')
            self.log.info(f"成功将 {len(new_dlcs_to_add)} 个新的无密钥/无Depot DLC合并到 {lua_filepath.name}")
        except Exception as e:
            self.log.error(f"添加无密钥DLC时出错: {self.stack_error(e)}")

    # --- MODIFIED: Rewritten file saving logic for local downloads ---
    async def _process_zip_manifest_generic(self, app_id: str, download_url: str, source_name: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        zip_path = self.temp_path / f'{app_id}.zip'
        extract_path = self.temp_path / app_id
        try:
            output_app_path = self.get_output_path_for_app(app_id)
            self.temp_path.mkdir(exist_ok=True, parents=True)
            self.log.info(f'正从 {source_name} 下载 AppID {app_id} 的清单...')
            response = await self.client.get(download_url, timeout=60)
            if response.status_code != 200:
                self.log.error(f'从 {source_name} 下载失败，状态码: {response.status_code}')
                return False
            async with aiofiles.open(zip_path, 'wb') as f: await f.write(response.content)
            self.log.info('正在解压...')
            with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(extract_path)

            if st_files := list(extract_path.glob('*.st')):
                st_converter = STConverter()
                for st_file in st_files:
                    try:
                        lua_content = st_converter.convert_file(str(st_file))
                        (st_file.with_suffix('.lua')).write_text(lua_content, encoding='utf-8')
                        self.log.info(f'已转换 {st_file.name} -> {st_file.with_suffix(".lua").name}')
                    except Exception as e:
                        self.log.error(f'转换 .st 文件 {st_file.name} 失败: {e}')
            
            manifest_files = list(extract_path.glob('*.manifest'))
            lua_files = list(extract_path.glob('*.lua'))

            # --- UNIFIED LOCAL SAVING LOGIC ---
            if not manifest_files: self.log.warning(f"在来自 {source_name} 的压缩包中未找到 .manifest 文件。")
            for f in manifest_files:
                shutil.copy2(f, output_app_path / f.name)
                self.log.info(f'已下载清单到: {output_app_path / f.name}')

            all_depots = {k: v for lua_f in lua_files for k, v in self.parse_lua_file_for_depots(str(lua_f)).items()}
            lua_filename = f"{app_id}.lua"
            lua_filepath = output_app_path / lua_filename
            addappid_lines = [f'addappid({app_id})']
            for depot_id, info in all_depots.items():
                key = info.get("DecryptionKey", "")
                addappid_lines.append(f'addappid({depot_id})' if not key or key.lower() == "none" else f'addappid({depot_id}, 1, "{key}")')
            
            setmanifestid_lines = []
            for manifest_f in manifest_files:
                if match := re.search(r'(\d+)_(\w+)\.manifest', manifest_f.name):
                    setmanifestid_lines.append(f'setManifestid({match.group(1)}, "{match.group(2)}")')

            async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
                await lua_file.write('\n'.join(addappid_lines) + '\n')
                if setmanifestid_lines:
                    await lua_file.write('\n-- Manifests\n')
                    await lua_file.write('\n'.join(setmanifestid_lines) + '\n')
            self.log.info(f"已生成解锁文件: {lua_filename}")

            if add_all_dlc: await self._add_free_dlcs_to_lua(app_id, lua_filepath)
            if patch_depot_key:
                self.log.info("开始修补创意工坊depotkey...")
                await self.patch_lua_with_depotkey(app_id, lua_filepath)
            
            self.log.info(f'成功处理来自 {source_name} 的清单。文件已保存至 {output_app_path.resolve()}')
            return True
        except Exception as e:
            self.log.error(f'处理来自 {source_name} 的清单时出错: {self.stack_error(e)}')
            return False
        finally:
            if zip_path.exists(): zip_path.unlink()
            if extract_path.exists(): shutil.rmtree(extract_path)

    async def process_printedwaste_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        return await self._process_zip_manifest_generic(app_id, f'https://api.printedwaste.com/gfk/download/{app_id}', "SWA V2 (printedwaste)", add_all_dlc, patch_depot_key)
    async def process_cysaw_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        return await self._process_zip_manifest_generic(app_id, f'https://cysaw.top/uploads/{app_id}.zip', "Cysaw", add_all_dlc, patch_depot_key)
    async def process_furcate_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        return await self._process_zip_manifest_generic(app_id, f'https://furcate.eu/files/{app_id}.zip', "Furcate", add_all_dlc, patch_depot_key)
    async def process_walftech_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        return await self._process_zip_manifest_generic(app_id, f'https://walftech.com/proxy.php?url=https%3A%2F%2Fsteamgames554.s3.us-east-1.amazonaws.com%2F{app_id}.zip', "Walftech", add_all_dlc, patch_depot_key)
    async def process_steamdatabase_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        return await self._process_zip_manifest_generic(app_id, f'https://steamdatabase.s3.eu-north-1.amazonaws.com/{app_id}.zip', "SteamDatabase", add_all_dlc, patch_depot_key)

    async def process_steamautocracks_v2_manifest(self, app_id: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        try:
            self.log.info(f'正从 SteamAutoCracks/ManifestHub(2) 处理 AppID {app_id} 的清单...')
            depot_manifest_map = await self._get_depots_and_manifests_from_steamui(app_id)
            if not depot_manifest_map:
                self.log.error(f"未能从 steamui API 获取到 AppID {app_id} 的 depot 信息，请检查APP ID是否正确或API请求问题")
                return False
            if 'IS_CN' not in os.environ: await self.checkcn()
            depotkeys_data = await self.download_depotkeys_json()
            if not depotkeys_data:
                self.log.error("无法获取 depotkeys 数据")
                return False
            valid_depots = {}
            for depot_id in depot_manifest_map.keys():
                if depot_id in depotkeys_data and (depotkey := str(depotkeys_data[depot_id]).strip()):
                    valid_depots[depot_id] = depotkey
                else:
                    self.log.warning(f"未找到或 depotkey 为空: depot {depot_id}")
            if not valid_depots:
                self.log.warning(f"AppID {app_id} 没有找到任何有效的 depot 密钥")
                return False
            # --- MODIFIED: Simplified logic for downloader ---
            return await self._process_steamautocracks_v2_for_downloader(app_id, valid_depots, depot_manifest_map, add_all_dlc, patch_depot_key, depotkeys_data)
        except Exception as e:
            self.log.error(f'处理 SteamAutoCracks/ManifestHub(2) 清单时出错: {self.stack_error(e)}')
            return False

    async def _get_depots_and_manifests_from_ddxnb(self, app_id: str) -> Dict[str, str]:
        """从备用API (steam.ddxnb.cn) 获取 depot 和对应的 manifest 信息"""
        try:
            url = f"https://steam.ddxnb.cn/v1/info/{app_id}"
            response = await self.client.get(url, timeout=20)
            response.raise_for_status()

            data = response.json()
            
            # Check for success status in the API response
            if data.get("status") != "success" or not data.get("data"):
                self.log.error(f"备用API返回错误或无数据 for AppID {app_id}，请检查APP ID是否正确或API请求问题")
                return {}

            app_data = data["data"].get(app_id)
            if not app_data or "depots" not in app_data:
                self.log.error(f"备用API响应中未找到 AppID {app_id} 的 depots 信息，可能此APP ID没有创意工坊密钥或者暂未收录，不影响本体使用")
                return {}
            
            depots = app_data["depots"]
            depot_manifest_map = {}

            for depot_id, depot_info in depots.items():
                if not depot_id.isdigit():
                    continue

                if isinstance(depot_info, dict):
                    manifests = depot_info.get("manifests", {})
                    public_manifest = manifests.get("public", {})
                    manifest_id = public_manifest.get("gid")

                    if manifest_id:
                        depot_manifest_map[depot_id] = str(manifest_id)
                        self.log.info(f"从备用API发现有效 depot: {depot_id}, manifest: {manifest_id}")

            if depot_manifest_map:
                self.log.info(f"从备用API总共找到 {len(depot_manifest_map)} 个有效的 depot 及其 manifest")
            else:
                self.log.warning(f"备用API未找到 AppID {app_id} 的任何有效 depot-manifest 映射，请检查APP ID是否正确，或API请求问题")

            return depot_manifest_map

        except Exception as e:
            self.log.error(f"从备用API (steam.ddxnb.cn) 获取 depot 信息失败: {e}")
            return {}
            

    async def _get_depots_and_manifests_from_steamui(self, app_id: str) -> Dict[str, str]:
        """从 steamui API 获取 depot 和对应的 manifest 信息，失败时使用备用API"""
        # 1. 尝试主API (steamui.com)
        vdf_content = "" # Initialize to ensure it exists for logging on failure
        try:
            self.log.info(f"正从主API (steamui.com) 获取 AppID {app_id} 的信息...")
            url = f"https://steamui.com/api/get_appinfo.php?appid={app_id}"
            response = await self.client.get(url, timeout=20)
            response.raise_for_status()
            
            vdf_content = response.text
            
            import vdf # Local import to avoid dependency issues if VDF is not always used
            data = vdf.loads(vdf_content)
            
            depot_manifest_map = {}
            
            # First-level check for depots
            for key, value in data.items():
                if key.isdigit() and isinstance(value, dict):
                    if 'manifests' in value and value['manifests']:
                        manifests = value['manifests']
                        if isinstance(manifests, dict) and 'public' in manifests:
                            public_manifest = manifests['public']
                            if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                manifest_id = public_manifest['gid']
                                depot_manifest_map[key] = manifest_id
            
            # Fallback checks for different VDF structures if first-level fails
            if not depot_manifest_map:
                if 'depots' in data:
                    depots = data['depots']
                    for depot_id, depot_info in depots.items():
                        if depot_id.isdigit() and isinstance(depot_info, dict):
                            if 'manifests' in depot_info and depot_info['manifests']:
                                manifests = depot_info['manifests']
                                if isinstance(manifests, dict) and 'public' in manifests:
                                    public_manifest = manifests['public']
                                    if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                        manifest_id = public_manifest['gid']
                                        depot_manifest_map[depot_id] = manifest_id
                
                if not depot_manifest_map:
                    for key, value in data.items():
                        if isinstance(value, dict) and 'depots' in value:
                            depots = value['depots']
                            for depot_id, depot_info in depots.items():
                                if depot_id.isdigit() and isinstance(depot_info, dict):
                                    if 'manifests' in depot_info and depot_info['manifests']:
                                        manifests = depot_info['manifests']
                                        if isinstance(manifests, dict) and 'public' in manifests:
                                            public_manifest = manifests['public']
                                            if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                                manifest_id = public_manifest['gid']
                                                depot_manifest_map[depot_id] = manifest_id

            if depot_manifest_map:
                self.log.info(f"从主API (steamui.com) 成功获取 {len(depot_manifest_map)} 个 depot。")
                return depot_manifest_map
            else:
                # This case means the request was successful but no depots were found.
                # We should raise an exception to trigger the fallback.
                raise ValueError("主API响应成功，但未解析到任何depot信息，请检查APP ID是否正确或API请求问题")

        except Exception as e:
            self.log.warning(f"主API (steamui.com) 访问或解析失败，请检查API及App id是否正常: {e}。")
            if vdf_content:
                self.log.warning(f"主API返回内容预览: {vdf_content[:300]}...")
            self.log.info("正在尝试备用API (steam.ddxnb.cn)...")
        
        # 2. 如果主API失败，调用备用API
        return await self._get_depots_and_manifests_from_ddxnb(app_id)

    # --- MODIFIED: Renamed from _for_steamtools to _for_downloader and adapted for local saving ---
    async def _process_steamautocracks_v2_for_downloader(self, app_id: str, valid_depots: Dict[str, str], depot_manifest_map: Dict[str, str], add_all_dlc: bool, patch_depot_key: bool, depotkeys_data: Dict) -> bool:
        try:
            output_app_path = self.get_output_path_for_app(app_id)
            lua_filename = f"{app_id}.lua"
            lua_filepath = output_app_path / lua_filename
            
            lines = [f'addappid({app_id})']
            for depot_id, depotkey in valid_depots.items():
                lines.append(f'addappid({depot_id}, 1, "{depotkey}")')
            
            manifest_lines = []
            for depot_id in valid_depots.keys():
                if depot_id in depot_manifest_map:
                    manifest_id = depot_manifest_map[depot_id]
                    manifest_lines.append(f'setManifestid({depot_id}, "{manifest_id}")')

            async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
                await lua_file.write('\n'.join(lines) + '\n')
                if manifest_lines:
                    await lua_file.write('\n-- Manifests\n')
                    await lua_file.write('\n'.join(manifest_lines) + '\n')
            
            self.log.info(f"已生成解锁文件: {lua_filename}")
            
            if add_all_dlc: await self._add_free_dlcs_to_lua(app_id, lua_filepath)
            if patch_depot_key:
                self.log.info("开始修补创意工坊depotkey...")
                await self._patch_lua_with_existing_depotkeys(app_id, lua_filepath, depotkeys_data)
            
            self.log.info(f"文件已保存至 {output_app_path.resolve()}")
            return True
        except Exception as e:
            self.log.error(f'为 Downloader 处理 SteamAutoCracks/ManifestHub(2) 清单时出错: {e}')
            return False
        
    async def _patch_lua_with_existing_depotkeys(self, app_id: str, lua_file_path: Path, depotkeys_data: Dict) -> bool:
        try:
            if app_id not in depotkeys_data:
                self.log.warning(f"没有此AppID的depotkey: {app_id},这是正常情况，可能此APP ID没有创意工坊密钥，或者暂未收录，不影响本体使用")
                return False
            depotkey = depotkeys_data[app_id]
            if not depotkey or not str(depotkey).strip():
                self.log.warning(f"AppID {app_id} 的 depotkey 为空或无效，跳过修补: '{depotkey}，这是正常情况，可能APP ID没有创意工坊密，或者暂未收录，不影响本体使用'")
                return False
            depotkey = str(depotkey).strip()
            self.log.info(f"找到 AppID {app_id} 的有效 depotkey: {depotkey}")
            if not lua_file_path.exists():
                self.log.error(f"LUA文件不存在: {lua_file_path}")
                return False
            async with aiofiles.open(lua_file_path, 'r', encoding='utf-8') as f:
                lua_content = await f.read()
            lines = lua_content.strip().split('\n')
            new_lines = []
            app_id_line_removed = False
            for line in lines:
                line = line.strip()
                if line == f"addappid({app_id})":
                    new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                    app_id_line_removed = True
                else:
                    new_lines.append(line)
            if not app_id_line_removed:
                new_lines.append(f'addappid({app_id},1,"{depotkey}")')
            async with aiofiles.open(lua_file_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(new_lines) + '\n')
            self.log.info(f"成功修补 LUA 文件的 depotkey: {lua_file_path.name}")
            return True
        except Exception as e:
            self.log.error(f"修补 LUA depotkey 时出错: {self.stack_error(e)}")
            return False
    
    async def fetch_branch_info(self, url: str, headers: Dict) -> Dict | None:
        try:
            r = await self.client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403: self.log.error("GitHub API请求次数已用尽。")
            elif e.response.status_code != 404: self.log.error(f"从 {url} 获取信息失败: {self.stack_error(e)}")
            return None
        except Exception as e:
            self.log.error(f'从 {url} 获取信息时发生意外错误: {self.stack_error(e)}')
            return None

    async def search_all_repos_for_appid(self, app_id: str, repos: List[str] = None) -> List[Dict]:
        if repos is None: repos = self.get_all_github_repos()
        github_token = self.config.get("Github_Personal_Token", "")
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        results = await asyncio.gather(*[self._search_single_repo(app_id, repo, headers) for repo in repos])
        return [res for res in results if res]

    async def _search_single_repo(self, app_id: str, repo: str, headers: Dict) -> Dict | None:
        self.log.info(f"正在仓库 {repo} 中搜索 AppID: {app_id}")
        url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
        r_json = await self.fetch_branch_info(url, headers)
        if r_json and 'commit' in r_json:
            tree_url = r_json['commit']['commit']['tree']['url']
            r2_json = await self.fetch_branch_info(tree_url, headers)
            if r2_json and 'tree' in r2_json:
                self.log.info(f"在 {repo} 中找到清单。")
                return {'repo': repo, 'sha': r_json['commit']['sha'], 'tree': r2_json['tree'], 'update_date': r_json["commit"]["commit"]["author"]["date"]}
        return None

    # --- MODIFIED: Rewritten file saving logic for local downloads ---
    async def process_github_manifest(self, app_id: str, repo: str, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        github_token = self.config.get("Github_Personal_Token", "")
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
        r_json = await self.fetch_branch_info(url, headers)
        if not (r_json and 'commit' in r_json):
            self.log.error(f'无法获取 {repo} 中 {app_id} 的分支信息。')
            return False
        sha = r_json['commit']['sha']
        tree_url = r_json['commit']['commit']['tree']['url']
        r2_json = await self.fetch_branch_info(tree_url, headers)
        if not (r2_json and 'tree' in r2_json):
            self.log.error(f'无法获取 {repo} 中 {app_id} 的文件列表。')
            return False
        files_to_download = r2_json.get('tree', [])
        if not files_to_download:
            self.log.warning(f"仓库 {repo} 的分支 {app_id} 为空。")
            return True
        try:
            tasks = [self._get_from_mirrors(sha, item['path'], repo) for item in files_to_download]
            downloaded_contents = await asyncio.gather(*tasks)
            downloaded_files = {item['path']: content for item, content in zip(files_to_download, downloaded_contents)}
        except Exception as e:
            self.log.error(f"下载文件失败，正在中止对 {app_id} 的处理: {e}")
            return False
        
        output_app_path = self.get_output_path_for_app(app_id)
        
        # --- UNIFIED LOCAL SAVING LOGIC ---
        for path, content in downloaded_files.items():
            if path.endswith('.manifest'):
                (output_app_path / Path(path).name).write_bytes(content)
                self.log.info(f"已下载清单: {Path(path).name}")

        all_depots = {}
        if key_vdf_path := next((p for p in downloaded_files if "key.vdf" in p.lower()), None):
            all_depots = vdf.loads(downloaded_files[key_vdf_path].decode('utf-8')).get('depots', {})

        lua_filename = f"{app_id}.lua"
        lua_filepath = output_app_path / lua_filename
        addappid_lines = [f'addappid({app_id})']
        for depot_id, info in all_depots.items():
            key = info.get("DecryptionKey", "")
            addappid_lines.append(f'addappid({depot_id})' if not key or key.lower() == "none" else f'addappid({depot_id}, 1, "{key}")')
        
        setmanifestid_lines = []
        for file_path in downloaded_files:
            if (match := re.search(r'(\d+)_(\w+)\.manifest', Path(file_path).name)):
                setmanifestid_lines.append(f'setManifestid({match.group(1)}, "{match.group(2)}")')

        async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
            await lua_file.write('\n'.join(addappid_lines) + '\n')
            if setmanifestid_lines:
                await lua_file.write('\n-- Manifests\n')
                await lua_file.write('\n'.join(setmanifestid_lines) + '\n')
        self.log.info(f"已生成解锁文件: {lua_filename}")
        
        if add_all_dlc: await self._add_free_dlcs_to_lua(app_id, lua_filepath)
        if patch_depot_key:
            self.log.info("开始修补创意工坊depotkey...")
            await self.patch_lua_with_depotkey(app_id, lua_filepath)
        
        self.log.info(f'清单最后更新时间: {r_json["commit"]["commit"]["author"]["date"]}')
        self.log.info(f'文件已保存至 {output_app_path.resolve()}')
        return True

    def extract_app_id(self, user_input: str) -> str | None:
        match = re.search(r"/app/(\d+)", user_input) or re.search(r"steamdb\.info/app/(\d+)", user_input)
        if match: return match.group(1)
        return user_input if user_input.isdigit() else None

    async def find_appid_by_name(self, game_name: str) -> List[Dict]:
        # --- 第一步：尝试主API (SteamUI) ---
        try:
            self.log.info(f"正在尝试通过主API搜索游戏: {game_name}")
            # 增加 timeout 防止卡住
            r = await self.client.get(f'https://steamui.com/api/loadGames.php?page=1&search={game_name}&sort=update', timeout=10)
            r.raise_for_status()
            games = r.json().get('games', [])
            
            if games:
                return games
            
            self.log.info("主API未找到结果，正在切换至备用API...")
            
        except Exception as e:
            self.log.warning(f"主API搜索出错: {e}，正在切换至备用API...")

        # --- 第二步：尝试备用API (Draoon Link) ---
        try:
            self.log.info(f"正在尝试通过备用API搜索: {game_name}")
            # 使用 params 传参，httpx 会自动处理中文URL编码
            url = "https://steam-lua.draoon.link/api/search"
            r_backup = await self.client.get(url, params={'term': game_name}, timeout=15)
            r_backup.raise_for_status()
            
            data = r_backup.json()
            
            # --- FIX START: 修复API解析逻辑 ---
            # API返回格式为 {"success":true, "games":[{...}, ...]}
            # 如果是字典且包含'games'键，则提取'games'列表
            if isinstance(data, dict) and 'games' in data:
                data = data['games']
            # --- FIX END ---
            
            # 字段包含 appid, name, schinese_name，与前端兼容
            if isinstance(data, list) and len(data) > 0:
                self.log.info(f"备用API成功找到 {len(data)} 个结果")
                return data
            else:
                self.log.warning("备用API也未找到相关游戏。")
                
        except Exception as e:
            self.log.error(f"搜索游戏 '{game_name}' 彻底失败 (备用API报错): {self.stack_error(e)}")
            
        return []

    async def cleanup_temp_files(self):
        try:
            if self.temp_path.exists():
                shutil.rmtree(self.temp_path)
                self.log.info('临时文件已清理。')
        except Exception as e:
            self.log.error(f'清理临时文件失败: {self.stack_error(e)}')