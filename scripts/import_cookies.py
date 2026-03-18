import json
import os
import sys
from pathlib import Path

# 将项目根目录添加到 Python 搜索路径
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from app.config import ConfigManager, cfg_get


def parse_netscape_cookies(file_path: str):
    """解析 Netscape/Mozilla cookies.txt 为标准 cookies 列表"""
    cookies = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) < 7:
                continue

            cookie = {
                "domain": parts[0],
                "path": parts[2],
                "secure": parts[3].upper() == "TRUE",
                "expires": int(parts[4]) if parts[4].isdigit() else -1,
                "name": parts[5],
                "value": parts[6],
                "httpOnly": False,
                "sameSite": "Lax",
            }
            cookies.append(cookie)
    return cookies


def normalize_json_cookies(raw_data):
    """
    兼容多种 JSON 导出格式：
    - 直接是 cookie 列表
    - {"cookies": [...]} 结构
    """
    if isinstance(raw_data, dict) and "cookies" in raw_data:
        raw_data = raw_data["cookies"]

    if not isinstance(raw_data, list):
        raise ValueError("JSON cookie 格式无效：不是列表")

    out = []
    for c in raw_data:
        if not isinstance(c, dict):
            continue
        out.append({
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "expires": int(c.get("expirationDate", c.get("expires", -1)) or -1),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
            "sameSite": c.get("sameSite", "Lax") or "Lax",
        })

    return out


def validate_critical_cookies(cookies):
    names = {c.get("name") for c in cookies}
    required_any = {"auth_token", "ct0"}
    missing = [k for k in required_any if k not in names]
    return missing


def import_cookies(file_path=None):
    # 自动寻找输入 cookie 文件
    if not file_path:
        for f in ["cookies.json", "cookies.txt"]:
            if os.path.exists(f):
                file_path = f
                break

    if not file_path or not os.path.exists(file_path):
        print("错误: 找不到 cookies.json 或 cookies.txt 文件。")
        print("请将导出的 Cookie 文件放入项目根目录。")
        return 1

    print(f"正在读取文件: {file_path} ...")

    try:
        if file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            cookies = normalize_json_cookies(raw_data)
        else:
            cookies = parse_netscape_cookies(file_path)
    except Exception as e:
        print(f"解析文件失败: {e}")
        return 1

    if not cookies:
        print("错误: 未能识别到有效的 Cookie 数据。")
        return 1

    # 过滤空 name/value
    cookies = [c for c in cookies if c.get("name") and c.get("value")]

    missing = validate_critical_cookies(cookies)
    if missing:
        print(f"⚠️ 警告: 缺少关键 Cookie: {missing}。后续可能无法抓取。")

    CONFIG_PATH = "./data/config.yaml"
    cfg = ConfigManager(CONFIG_PATH).load()
    out_file = cfg_get(cfg, "x.cookies_file", "./data/x_cookies.json")

    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

    print(f"✅ 已导出 {len(cookies)} 条 cookies 到: {out_path}")
    print("下一步：启动程序后验证 Twikit 是否能读取并抓取用户推文。")
    return 0


if __name__ == "__main__":
    fp = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(import_cookies(fp))
