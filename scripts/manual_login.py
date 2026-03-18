import sys
import os
from pathlib import Path

# 将项目根目录添加到 Python 搜索路径
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from app.x_browser import XBrowser
from app.config import ConfigManager, cfg_get

CONFIG_PATH = "./data/config.yaml"

cfg = ConfigManager(CONFIG_PATH).load()
user_data_dir = cfg_get(cfg, "x.user_data_dir", "./data/x_profile")
headless = bool(cfg_get(cfg, "x.headless", False))

x = XBrowser(user_data_dir=user_data_dir, headless=headless)
x.manual_login()
