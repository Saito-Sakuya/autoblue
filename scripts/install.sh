#!/usr/bin/env bash



set -euo pipefail







APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"



VENV_DIR="$APP_DIR/.venv"



PYTHON_BIN=""







echo "[INFO] AutoBlue2 安装脚本（统一依赖入口�?







auto_pick_python() {



  if [[ -x "$VENV_DIR/bin/python" ]]; then



    PYTHON_BIN="$VENV_DIR/bin/python"



    return



  fi



  if command -v python3 >/dev/null 2>&1; then



    PYTHON_BIN="python3"



    return



  fi



  echo "[ERROR] 未找�?python3，请先安�?Python 3.10+"



  exit 1



}







create_or_use_venv() {



  if [[ ! -d "$VENV_DIR" ]]; then



    echo "[INFO] 创建虚拟环境: $VENV_DIR"



    python3 -m venv "$VENV_DIR"



  else



    echo "[INFO] 复用虚拟环境: $VENV_DIR"



  fi







  # shellcheck disable=SC1091



  source "$VENV_DIR/bin/activate"



  PYTHON_BIN="$VENV_DIR/bin/python"



  echo "[INFO] Python: $($PYTHON_BIN -V)"



}







install_requirements() {



  echo "[INFO] 升级 pip/setuptools/wheel ..."



  "$PYTHON_BIN" -m pip install --upgrade pip wheel setuptools







  echo "[INFO] 安装项目依赖（requirements.txt�?.."



  "$PYTHON_BIN" -m pip install -r "$APP_DIR/requirements.txt"



}







verify_runtime() {



  echo "[INFO] 校验关键依赖可导�?.."



  "$PYTHON_BIN" - << 'PY'



import importlib



mods = ["yaml", "twikit", "telegram", "apscheduler"]



missing = []



for m in mods:



    try:



        importlib.import_module(m)



    except Exception:



        missing.append(m)



if missing:



    raise SystemExit("missing modules: " + ", ".join(missing))



print("runtime dependency check: OK")



PY



}







post_install_hint() {



  cat << 'MSG'







[OK] 安装完成�?



若下一步无反应，请手动执行以下命令�?



  source .venv/bin/activate



  bash scripts/menu.sh



MSG



}







main() {



  auto_pick_python



  create_or_use_venv



  install_requirements



  verify_runtime



  post_install_hint







  # 引导进入配置菜单



  echo



  read -p "是否执行配置程序？Y/N（Y�? " choice



  choice=${choice:-Y}



  if [[ "$choice" =~ ^[Yy]$ ]]; then



    if [[ -f "$APP_DIR/scripts/menu.sh" ]]; then



      chmod +x "$APP_DIR/scripts/menu.sh" 2>/dev/null || true



      exec bash "$APP_DIR/scripts/menu.sh"



    else



      echo "[ERROR] 未找�?$APP_DIR/scripts/menu.sh"



    fi



  fi



}







main "$@"