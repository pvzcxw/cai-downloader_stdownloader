# Cai Downloader - Steam 游戏清单下载工具

**版本：v1.4**  
**作者：pvzcxw**  
**许可证：MIT License **

> 一个用于从多个公开清单仓库下载 Steam 游戏清单（.manifest）并生成解锁脚本（.lua）的命令行工具。支持批量处理 AppID、创意工坊物品，以及自定义清单库。

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![License](https://img.shields.io/badge/License-GPLv3-green) ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

本软件及cai install全系已完全停更，详细信息：

Cai install Official全系列于2026年6月停更

人话：我不做软件了

全系已换MIT协议，即将软件还是显示GPL3.0

停更通知：

从2023年，到现在，我们一起走过了3个春夏秋冬，但，落日终归海，入库圈的环境已经腻了，这个圈子固然是乌烟瘴气的，倒卖，恶俗，各家互斗，一次次的，对我来说，入库圈已不是我乐趣所在了，而是一种负担，折磨。从一次倒卖，被背刺，辱骂，都是对我的伤害。很多次，都是强行忍受，对我而言没有益处。

而且，清单下载器做久了也就那样，没什么新鲜感了，cai install走到现在，仅凭热爱，在25-26两年间，cai install xp，cai install gui，cai install web ui等，一共陆续更新了70多个版本，平均每5天更新一次，但现在这份热爱已消失了。

我已经想停更好久了，感觉继续下去没什么意思了，cai install这个工具能让大家喜欢，我也很开心，在入库圈有一定名誉，也是大家一齐的努力结果。

另一方面，步入高中，我也不想再把注意力放在这里。

Cai install全系（cai install xp，cai install GUI，cai install web ui，cai install reborn）将以MIT开源，欢迎大家二改！继承cai install的ip精神！

仙人指路：以后，如果大家还想使用免费工具，可以使用SteamToolbox(菜玩社区下载），keysteam(bilibili下载），fluent install(cai install fork二改项目）这些都是我认为不错的工具。

这次停更，也许是分离，但是我认为cai install这个IP会留在大家心里。

2023-2026 —PVZCXW

---

## ✨ 功能特点

- 📥 **多源清单下载** – 支持以下内置仓库：
  - SWA V2 (printedwaste)
  - Cysaw
  - Furcate
  - Walftech
  - SteamDatabase
  - SteamAutoCracks/ManifestHub (v2 方案，含 depotkey 自动合并)
  - 清单不求人（仅清单，无密钥）
- 🧩 **创意工坊支持** – 通过物品 ID 或 URL 直接下载创意工坊的清单文件。
- 🔍 **智能游戏搜索** – 输入游戏名称自动搜索 AppID（支持 SteamUI 和备用 API）。
- 🛠️ **自定义清单库** – 可在配置文件中添加任意 GitHub 仓库或 ZIP 下载源。
- 📦 **批量处理** – 一次输入多个 AppID 或创意工坊链接（英文逗号分隔）。
- ⚙️ **附加功能**：
  - 自动添加该游戏的所有可用 DLC（无密钥/无 Depot 的 DLC）。
  - 自动修补创意工坊密钥（depotkey）到生成的 `.lua` 文件中。
- 🌐 **网络优化** – 自动检测国内/海外环境，使用 GitHub 镜像加速下载。
- 🔄 **自动更新检测** – 启动时检查 GitHub 新版发布，提供下载链接。

---

## 🖥️ 系统要求

- **操作系统**：Windows / Linux / macOS（本工具为纯 Python 命令行工具，无需 Steam 客户端）
- **Python 版本**：3.9 或更高
- **依赖库**：见下方安装说明

---

## 📦 安装与使用

### 1. 获取源码

```bash
git clone https://github.com/pvzcxw/cai-downloader_stdownloader.git
cd cai-downloader_stdownloader
```

或直接下载 ZIP 包解压。

### 2. 安装依赖

建议使用虚拟环境：

```bash
# 创建虚拟环境（可选）
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate    # Linux/macOS

# 安装依赖
pip install httpx aiofiles vdf colorama colorlog ujson
```

> 注：标准库 `asyncio`, `json`, `zipfile`, `pathlib` 等无需额外安装。

### 3. 运行程序

```bash
python frontend_cli.py
```

首次运行会自动生成 `config.json` 配置文件。

---

## 🚀 使用说明

### 主菜单

启动后进入交互式菜单：

```
请选择要执行的操作：
1. 下载游戏文件 (清单和LUA)
2. 下载创意工坊文件 (仅清单)
q. 退出程序
```

### 1. 下载游戏文件

#### 输入 AppID 或游戏名称

- 直接输入数字 AppID（如 `730`）
- 输入 Steam 商店链接（如 `https://store.steampowered.com/app/730/`）
- 输入 SteamDB 链接（如 `https://steamdb.info/app/730/`）
- 输入游戏名称（如 `Counter-Strike 2`），程序会搜索并列出匹配的游戏供选择。

支持批量处理，用英文逗号分隔：`730, 570, 440`

#### 附加选项

- **是否添加所有 DLC**：选择 `y` 将自动查找并添加该游戏所有可用的免费 DLC（无密钥的 Depot）。
- **是否修补创意工坊密钥**：选择 `y` 将尝试从 `depotkeys.json` 获取该游戏的创意工坊密钥，并写入 `.lua` 文件中。

#### 选择清单源

- **从指定清单库中选择**：程序列出所有内置仓库 + 自定义仓库，输入编号即可。
- **在所有 GitHub 清单库中搜索**：自动扫描内置和自定义的 GitHub 仓库，找到包含该 AppID 分支的仓库，让用户选择使用哪一个。

### 2. 下载创意工坊文件

输入创意工坊物品的 ID 或完整 URL（支持批量，逗号分隔），程序会自动查询物品所属的游戏 AppID 和 manifest ID，并下载对应的清单文件。

示例：
- 仅 ID：`2833657835`
- 完整 URL：`https://steamcommunity.com/sharedfiles/filedetails/?id=2833657835`

### 输出文件

所有下载的文件保存在 `./cai_downloads/<AppID>/` 目录下：

- `*.manifest` – 清单文件（原始文件名如 `depotID_manifestID.manifest`）
- `<AppID>.lua` – 生成的解锁脚本，包含 `addappid` 和 `setManifestid` 指令

---

## ⚙️ 配置文件 `config.json`

位于程序根目录，首次启动自动生成。结构如下：

```json
{
    "Github_Personal_Token": "",
    "Custom_Repos": {
        "github": [],
        "zip": []
    },
    "QA1": "...",
    "QA2": "...",
    "QA3": "...",
    "QA4": "..."
}
```

### 配置项说明

| 字段 | 说明 |
|------|------|
| `Github_Personal_Token` | GitHub 个人访问令牌（可选）。配置后可提高 API 请求限额（5000次/小时），[获取方法](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| `Custom_Repos.github` | 自定义 GitHub 仓库列表。每个元素为 `{"name": "显示名称", "repo": "用户名/仓库名"}` |
| `Custom_Repos.zip` | 自定义 ZIP 清单库列表。每个元素为 `{"name": "显示名称", "url": "下载URL，用{app_id}作为占位符"}` |

### 自定义仓库示例

```json
"Custom_Repos": {
    "github": [
        {"name": "我的私人仓库", "repo": "myuser/myrepo"}
    ],
    "zip": [
        {"name": "我的ZIP源", "url": "https://example.com/{app_id}.zip"}
    ]
}
```

---

## ❓ 常见问题

### 1. 程序运行后提示“无法加载配置”？

删除 `config.json` 并重启程序，会自动生成默认配置。

### 2. 为什么有些游戏的清单下载失败？

可能原因：
- 该游戏在所选的清单库中没有收录（建议使用“在所有 GitHub 库中搜索”模式）。
- 网络问题导致下载超时（国内用户建议使用镜像，程序已自动启用）。
- GitHub API 请求次数用尽（未配置 Token 时每小时 60 次），请稍后再试或配置 Token。

### 3. 生成的 `.lua` 文件如何使用？

- 如果你是 **SteamTools** 用户：将 `.lua` 文件放入 `Steam/config/stplug-in/` 目录，重启 Steam 即可。
- 如果你是 **GreenLuma** 用户：需要使用本工具生成的 `.lua` 内容手动处理（本工具不直接支持 GreenLuma 的文件部署，仅提供清单和密钥）。

> 注意：Cai Downloader 本身 **不负责** 将文件安装到 Steam 目录，它只是一个下载器。后续集成请参考相关解锁工具的文档。

### 4. 创意工坊下载的文件放在哪里？

与游戏文件相同，保存在 `./cai_downloads/<consumer_appid>/` 目录下，文件名为 `<consumer_appid>_<manifestID>.manifest`。

### 5. 能否在非 Windows 系统上使用？

可以，本工具是纯 Python 命令行工具，只要安装 Python 依赖即可在 Linux/macOS 上运行。生成的 `.lua` 文件也可跨平台使用。

### 6. 如何更新程序？

程序启动时会自动检查 GitHub 发布页的新版本，并弹出更新提示，点击“立即更新”将打开浏览器跳转到下载页面，手动下载新版替换即可。

---

## 📄 开源协议

本项目基于 **MIT License** 开源。  

---

## 🙏 致谢与联系

- **作者**：pvzcxw  
- **官方 QQ 群**：993782526  
- **Bilibili**：[菜Games-pvzcxw](https://space.bilibili.com/49307545) 

> 本项目完全免费，请勿用于商业用途。如有问题请在 GitHub 仓库提交 Issue 或加入 QQ 群反馈。

---

**Happy downloading! 🎮**
