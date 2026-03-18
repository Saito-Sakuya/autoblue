# AutoBlue

基于 Twikit + Telegram + AI 的 X (Twitter) 信息抓取、筛选与推送工具。集成自动化安装、交互式配置菜单、多语言支持及当日动态智能筛选。

---

## 目录

- [AutoBlue](#autoblue)
  - [目录](#目录)
  - [核心能力](#核心能力)
  - [运行环境](#运行环境)
  - [快速安装 (Linux)](#快速安装-linux)
  - [快速安装 (Docker)](#快速安装-docker)
  - [配置与启动](#配置与启动)
  - [Telegram 指令手册](#telegram-指令手册)
    - [核心设置](#核心设置)
    - [关注管理](#关注管理)
    - [AI 与策略调整](#ai-与策略调整)
  - [抓取逻辑说明](#抓取逻辑说明)
  - [鸣谢](#鸣谢)
  - [免责声明](#免责声明)
  - [许可证](#许可证)

---

## 核心能力

- **智能抓取**：基于 Twikit 模拟抓取指定账号动态，仅处理 UTC 当天推文。
- **AI 筛选**：支持自定义模型、API 地址、筛选提示词、Max Tokens 及阈值（keep_threshold）。
- **审核推送**：Telegram 机器人提供实时审核（通过/忽略），支持待发布任务队列。
- **批量管理**：支持 URL、@用户名、纯用户名增量导入关注列表，自动去重。
- **配置工具**：提供交互式管理脚本，一站式管理配置、导入 Cookie 及查看状态。

## 运行环境

本项目支持主流 Linux 服务器环境：
- **系统要求**：Linux (Debian/Ubuntu 等主流发行版)
- **架构支持**：amd64 (x86_64) 及 arm64 (aarch64)
- **依赖工具**：Python 3.10+ 或 Docker

---

## 快速安装 (Linux)

1. **执行安装脚本**：
   ```bash
   bash scripts/install.sh
   ```
   该脚本会自动创建虚拟环境、安装依赖并校验环境。

2. **启动菜单进行配置**：
   ```bash
   bash scripts/menu.sh
   ```

---

## 快速安装 (Docker)

1. **拉取代码并启动容器**：
   ```bash
   git clone https://github.com/Saito-Sakuya/autoblue
   cd autoblue
   docker-compose up -d
   ```

2. **进入交互式配置菜单**：
   ```bash
   docker exec -it autoblue bash scripts/menu.sh
   ```
   在菜单中完成 Bot Token、Chat ID 和 AI 参数的设置。

3. **导入 Cookie**：
   将 `cookies.json` 或 `cookies.txt` 放入项目的 `data/` 目录，或在上述菜单中选择“导入 Cookie”。

4. **应用配置**：
   配置完成后，重启容器：
   ```bash
   docker-compose restart
   ```

---

## 配置与启动

推荐始终使用 `scripts/menu.sh` 进行操作：

- **实时状态**：自动显示当前配置摘要及主程序运行状态。
- **一键配置**：设置 Bot Token、Chat ID、AI 参数（模型、API 地址等）。
- **Cookie 导入**：自动识别根目录或 data 目录下的 Cookie 文件并导入。
- **快捷启动**：支持普通启动或后台静默启动。

---

## Telegram 指令手册

### 核心设置
- `/help` - 显示指令手册
- `/run` - 手动触发全量抓取与 AI 筛选
- `/status` - 查看运行状态摘要
- `/queue` - 查看待发布任务队列
- `/setchat` - 将当前窗口设为推送目标
- `/allowme` - 绑定当前账号为管理员

### 关注管理
- `/set_following_url ...` - 增量添加 URL/@用户名/纯用户名（输入 clear 可清空）
- `/show_following [页码]` - 查看当前关注列表
- `/refresh_following` - 校验关注列表

### AI 与策略调整
- `/show_ai` - 查看 AI 详细配置及提示词
- `/set_model <model>` - 修改 AI 模型
- `/set_api_url <url>` - 修改 API 地址
- `/set_api_key <key>` - 修改 API Key
- `/set_threshold <0~1>` - 修改筛选阈值
- `/set_ai_filter <内容>` - 修改 AI 筛选提示词
- `/set_max_tokens <长度>` - 修改 AI 输出最大长度
- `/test_model` - 模型连通性自检

---

## 抓取逻辑说明

- **日期筛选**：系统会自动过滤推文，仅保留 UTC 时间当天的动态。
- **数量限制**：通过 `fetch.max_tweets_per_user` 限制每个用户的抓取深度。
- **增量策略**：所有设置关注列表的操作均采用增量追加 + 自动去重模式。

---

## 鸣谢

本项目的基础抓取能力由以下优秀的开源项目提供支持：

- **[Twikit](https://github.com/d60/twikit)**：感谢提供的非官方 X (Twitter) API 交互库，为本项目的核心数据抓取提供了可能。

**开发模式说明**：
- 本项目大部分代码采用 **Vibe Coding** 模式完成。感谢各类优秀的 AI 编程助手（Gemini CLI / Codex / LLMs ）在代码生成、查错与重构中提供的强大生产力，让开发者实现高效快速开发落地。

---

## 免责声明

- **账号风险**：本项目基于网页模拟抓取数据。使用此工具可能违反 X 的服务条款，存在账号被限流、冻结或封禁的风险。
- **使用建议**：强烈建议使用全新的备用账号进行测试，请勿使用重要资产账号。
- **责任豁免**：本项目仅供技术交流与学习。开发者对因使用本项目导致的任何账号损失或法律纠纷概不负责。

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
底层依赖项目 Twikit同样基于 MIT License。
