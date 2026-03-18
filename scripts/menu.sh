#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f /data/config.yaml ]]; then
  CONFIG_PATH="/data/config.yaml"
else
  CONFIG_PATH="${CONFIG_PATH:-$APP_DIR/data/config.yaml}"
fi

if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  PY="$APP_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "[ERROR] Python not found"
  exit 1
fi

CFG="$APP_DIR/scripts/cfg.py"

prompt() {
  local msg="$1"; local def="${2:-}"
  read -r -p "$msg [$def]: " ans || true
  echo "${ans:-$def}"
}

get_cfg() {
  $PY "$CFG" --config "$CONFIG_PATH" get "$1" 2>/dev/null || true
}

set_cfg() {
  local path="$1"; local value="$2"; local typ="${3:-str}"
  $PY "$CFG" --config "$CONFIG_PATH" set "$path" "$value" --type "$typ" >/dev/null
}

show_summary() {
  echo "--- 当前配置摘要 ---"
  echo "telegram.bot_token: $(get_cfg telegram.bot_token | sed 's/./*/g' | cut -c1-8)..."
  echo "telegram.chat_id:   $(get_cfg telegram.chat_id)"
  echo "x.cookies_file:    $(get_cfg x.cookies_file)"
  count=$($PY -c "import yaml, sys; v=yaml.safe_load(sys.stdin); print(len(v) if isinstance(v, list) else 0)" <<< "$(get_cfg x.following_users)")
  echo "x.following_users: $count 个账号"
  echo "x.language:        $(get_cfg x.language)"
  echo "fetch.interval:    $(get_cfg fetch.interval_minutes)"
  echo "ai.model:          $(get_cfg ai.model)"

  # 检测运行状态
  if pgrep -f "python3 -m app.main" > /dev/null; then
    echo -e "运行状态:          \e[32m正在运行 (Running)\e[0m"
  else
    echo -e "运行状态:          \e[31m未运行 (Stopped)\e[0m"
  fi
  echo "--------------------"
}

import_cookie() {
  if [[ -f "$APP_DIR/cookies.txt" ]]; then
    $PY "$APP_DIR/scripts/import_cookies.py" "$APP_DIR/cookies.txt"
  elif [[ -f "$APP_DIR/cookies.json" ]]; then
    $PY "$APP_DIR/scripts/import_cookies.py" "$APP_DIR/cookies.json"
  else
    echo "未找到 cookies.txt 或 cookies.json，请先放到项目根目录。"
    return
  fi
}

while true; do
  echo
  echo -e "\e[33m[NOTICE] 欢迎使用AutoBlue！你需要在此页面中完成全部选项的设置方可启动主程序！\e[0m"
  echo "====== AutoBlue2 (Twikit) 菜单 ======"
  echo "1) 刷新配置摘要"
  echo "2) 设置 Telegram Bot Token"
  echo "3) 设置 Telegram Chat ID"
  echo "4) 导入 Cookie（cookies.txt/json）"
  echo "5) 设置 x.cookies_file（默认路径无需设置）"
  echo "6) 设置 x.following_users（逗号分隔，用作测试）"
  echo "7) 设置 x.language（zh/en）"
  echo "8) 设置抓取间隔（分钟）"
  echo "9) 设置 AI（api_url/api_key/model）"
  echo "10) 启动主程序（前台运行）"
  echo "11) 启动主程序（静默启动）"
  echo "0) 退出"
  echo
  show_summary
  read -r -p "> " c

  case "$c" in
    1)
      # 仅刷新，循环会自动调用 show_summary
      ;;

    2)
      tok=$(prompt "请输入 telegram.bot_token" "$(get_cfg telegram.bot_token)")
      set_cfg telegram.bot_token "$tok" str
      echo "OK"
      ;;
    3)
      cid=$(prompt "请输入 telegram.chat_id" "$(get_cfg telegram.chat_id)")
      set_cfg telegram.chat_id "$cid" int
      echo "OK"
      ;;
    4)
      import_cookie
      ;;
    5)
      cf=$(prompt "请输入 x.cookies_file" "$(get_cfg x.cookies_file)")
      set_cfg x.cookies_file "$cf" str
      echo "OK"
      ;;
    6)
      fu=$(prompt "请输入要添加的 x.following_users（逗号分隔）" "")
      if [[ -n "$fu" ]]; then
        # 获取现有列表，清除 YAML 的列表格式符号 (- 和 [])，转换为逗号分隔
        current_fu=$(get_cfg x.following_users | tr -d '[]\n' | sed 's/^- //g' | tr '-' ',' | tr ' ' ',' | tr -s ',' | sed 's/^,//;s/,$//')

        # 兼容处理：如果 get_cfg 返回的是多行 - name 格式，上面的 tr 处理可能不够完美，
        # 我们用一个更稳健的方式从 YAML 中提取列表项：
        current_fu_clean=$($PY -c "import yaml, sys; cfg=yaml.safe_load(sys.stdin); print(','.join(cfg) if isinstance(cfg, list) else '')" <<< "$(get_cfg x.following_users)")

        if [[ -n "$current_fu_clean" ]]; then
          merged_fu="$current_fu_clean,$fu"
        else
          merged_fu="$fu"
        fi
        # 利用 python 进行去重并过滤掉无效字符（如多余的横杠或空括号）
        deduped_fu=$($PY -c "import sys; print(','.join(dict.fromkeys(s.strip().lstrip('@').lstrip('-') for s in sys.argv[1].split(',') if s.strip() and s.strip() not in ('[]', ''))))" "$merged_fu")
        set_cfg x.following_users "$deduped_fu" list
        echo "已增量添加并去重，当前共 $(echo "$deduped_fu" | tr ',' '\n' | grep -v '^$' | wc -l | xargs) 个账号"
      else
        echo "未输入内容，跳过"
      fi
      echo "OK"
      ;;

    7)
      lg=$(prompt "请输入 x.language (zh/en)" "$(get_cfg x.language)")
      set_cfg x.language "$lg" str
      echo "OK"
      ;;
    8)
      iv=$(prompt "请输入 fetch.interval_minutes" "$(get_cfg fetch.interval_minutes)")
      set_cfg fetch.interval_minutes "$iv" int
      echo "OK"
      ;;
    9)
      url=$(prompt "ai.api_url（https://api.openai.com）" "$(get_cfg ai.api_url)")
      key=$(prompt "ai.api_key" "$(get_cfg ai.api_key)")
      mdl=$(prompt "ai.model" "$(get_cfg ai.model)")
      set_cfg ai.api_url "$url" str
      set_cfg ai.api_key "$key" str
      set_cfg ai.model "$mdl" str
      echo "OK"
      ;;
    10)
      echo "[INFO] 正在启动主程序..."
      cd "$APP_DIR"
      if [[ -f "$APP_DIR/.venv/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$APP_DIR/.venv/bin/activate"
      fi
      python3 -m app.main
      exit 0
      ;;
    11)
      echo "[INFO] 正在后台启动主程序 (静默模式)..."
      cd "$APP_DIR"
      if [[ -f "$APP_DIR/.venv/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$APP_DIR/.venv/bin/activate"
      fi
      nohup python3 -m app.main > app.log 2>&1 &
      echo "[OK] 主程序已在后台启动，日志将写入 app.log"
      echo "可以使用 'tail -f app.log' 查看实时日志。"
      ;;
    0)
      exit 0
      ;;
    *)
      echo "无效选项"
      ;;
  esac
done
