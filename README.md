# AutoBlue

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey.svg)
![Arch](https://img.shields.io/badge/Architecture-amd64%20%7C%20arm64-success.svg)
![Vibe Coding](https://img.shields.io/badge/Developed_with-Vibe_Coding-8A2BE2.svg)

基于 **Twikit + Telegram + AI** 的 X(Twitter) 信息抓取、筛选与推送工具。  
集成自动化安装、交互式配置菜单、多语言支持及当日动态智能筛选。

---

## 📑 目录

- [AutoBlue](#autoblue)
  - [📑 目录](#-目录)
  - [✨ 核心能力](#-核心能力)
  - [🌍 运行环境](#-运行环境)
  - [🚀 快速安装](#-快速安装)
  - [🛠️ 配置与启动 (交互式)](#️-配置与启动-交互式)
  - [⚙️ 最小手动配置 (可选)](#️-最小手动配置-可选)
  - [🤖 Telegram 命令手册](#-telegram-命令手册)
    - [核心设置](#核心设置)
    - [Following 管理](#following-管理)
    - [AI 与策略调整](#ai-与策略调整)
  - [🧠 抓取逻辑说明](#-抓取逻辑说明)
  - [💖 鸣谢 (Acknowledgments)](#-鸣谢-acknowledgments)
  - [⚠️ 免责声明 (Disclaimer)](#️-免责声明-disclaimer)
  - [📄 许可证](#-许可证)

---

## ✨ 核心能力

- **智能抓取**：基于 Twikit 模拟抓取指定账号动态，**仅处理当日（UTC）推文**。
- **AI 筛选**：支持自定义模型、API 地址、筛选提示词、Max Tokens 及阈值（`keep_threshold`）。
- **审核推送**：Telegram 机器人提供实时审核（通过/忽略），支持待发布任务队列。
- **批量管理**：支持 URL、@用户名、纯用户名**增量导入**关注列表，自动去重。
- **交互菜单**：提供 `scripts/menu.sh` 一站式管理配置、导入 Cookie、查看运行状态及启动程序。

## 🌍 运行环境

本项目全面支持主流 Linux 服务器环境：
- **系统要求**：Linux (高度兼容 Debian/Ubuntu 等主流发行版)
- **架构支持**：`amd64` (x86_64) 及 `arm64` (aarch64)

---

## 🚀 快速安装

> 统一入口：`scripts/install.sh`  
> 该脚本会自动处理虚拟环境创建、依赖安装及环境校验，并自动修复脚本执行权限。

```bash
bash scripts/install.sh
````

**安装完成后**：
脚本会提示“是否执行配置程序？Y/N”，输入 `Y` 或回车即可进入交互式配置菜单。

-----

## 🛠️ 配置与启动 (交互式)

推荐使用 **`scripts/menu.sh`** 进行所有后续操作：

```bash
bash scripts/menu.sh
```

**菜单功能亮点：**

  - **实时状态**：自动显示当前配置摘要及主程序运行状态（Running/Stopped）。
  - **一键配置**：设置 Bot Token、Chat ID、AI 参数（模型、API、提示词等）。
  - **Cookie 导入**：自动识别根目录下的 `cookies.txt` 或 `cookies.json` 并导入。
  - **快捷启动**：支持“普通启动”或“静默启动（后台运行，日志存入 app.log）”。

-----

## ⚙️ 最小手动配置 (可选)

若需手动修改 `data/config.yaml`，请确保包含以下核心项：

```yaml
telegram:
  bot_token: "<YOUR_BOT_TOKEN>"
  chat_id: 123456789

x:
  cookies_file: "./data/x_cookies.json"
  following_users: ["smee_official"] # 增量模式下，新账号会自动追加至此列表
  language: "zh"

ai:
  api_url: "[https://api.openai.com](https://api.openai.com/无需输入v1)"
  api_key: "<YOUR_API_KEY>"
  model: "gpt-4o-mini"
  prompt_filter: "你的任务是从社交媒体内容中筛选“真正重要的信息”..."
  max_tokens: 800
```

-----

## 🤖 Telegram 命令手册

### 核心设置

  - `/help` - 显示指令手册
  - `/run` - 手动触发全量抓取与 AI 筛选
  - `/status` - 查看运行状态摘要
  - `/queue` - 查看待发布任务队列
  - `/setchat` - 将当前窗口设为推送目标
  - `/allowme` - 绑定当前账号为管理员

### Following 管理

  - `/set_following_url ...` - **增量添加** URL/@用户名/纯用户名（输入 `clear` 可清空）
  - `/show_following [页码]` - 查看当前关注列表
  - `/refresh_following` - 校验关注列表（Twikit 语义同步）

### AI 与策略调整

  - `/show_ai` - 查看 AI 详细配置（**支持显示完整长提示词**，最高 3000 字符）
  - `/set_model <model>` - 修改 AI 模型
  - `/set_api_url <url>` - 修改 API 地址
  - `/set_api_key <key>` - 修改 API Key
  - `/set_threshold <0~1>` - 修改筛选阈值
  - `/set_ai_filter <内容>` - 修改 AI 筛选提示词
  - `/set_max_tokens <长度>` - 修改 AI 输出最大长度
  - `/test_model` - 模型连通性自检

-----

## 🧠 抓取逻辑说明

  - **日期筛选**：系统现在会自动过滤推文，**仅保留 UTC 时间当天的动态**。
  - **数量限制**：通过 `fetch.max_tweets_per_user` 限制每个用户的抓取深度，确保时效性。
  - **增量策略**：所有设置关注列表的操作（Bot/Menu）均采用**增量追加 + 自动去重**模式，保护现有配置不被覆盖。

-----

## 💖 鸣谢 (Acknowledgments)

本项目的基础抓取能力由以下优秀的开源项目提供支持：

  - **[Twikit](https://github.com/d60/twikit)**：感谢提供的非官方 X (Twitter) API 交互库，为本项目的核心数据抓取提供了可能。

**开发模式说明**：
- 本项目大部分代码采用 **Vibe Coding** 模式完成。感谢各类优秀的 AI 编程助手（GeminiCLI / Codex / LLMs 等）在代码生成、查错与重构中提供的强大生产力，让开发者实现高效快速开发落地。
-----

## ⚠️ 免责声明 (Disclaimer)

  - **账号风险**：本项目基于网页模拟/非官方接口抓取数据。使用此工具可能违反 X (Twitter) 的服务条款，**存在极高的账号被限流、冻结或永久封禁的风险**。
  - **使用建议**：强烈建议您使用**全新注册的备用账号**进行运行和测试，**绝对不要**使用您的主力账号或包含重要资产的账号。
  - **责任豁免**：本项目仅供技术交流与学习使用。开发者对因使用本项目导致的任何账号损失、数据泄露或法律纠纷概不负责。请在遵守当地法律法规的前提下使用。

-----

## 📄 许可证

本项目采用 [MIT License](https://www.google.com/search?q=LICENSE) 开源。  
底层依赖项目 Twikit 同样基于 MIT License。
