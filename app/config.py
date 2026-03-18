import os
import time
from dataclasses import dataclass
from typing import Any, Dict

import yaml


class ConfigError(Exception):
    pass


@dataclass
class ConfigManager:
    path: str
    _mtime: float = 0.0
    _cfg: Dict[str, Any] | None = None

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            raise ConfigError(f"Config not found: {self.path}")
        with open(self.path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        self._cfg = cfg
        self._mtime = os.path.getmtime(self.path)
        return cfg

    def get(self) -> Dict[str, Any]:
        if self._cfg is None:
            return self.load()
        return self._cfg

    def reload_if_changed(self) -> bool:
        try:
            mtime = os.path.getmtime(self.path)
        except FileNotFoundError:
            return False
        if mtime > self._mtime + 1e-6:
            self.load()
            return True
        return False

    def save(self, cfg: Dict[str, Any]) -> None:
        tmp = f"{self.path}.tmp.{int(time.time())}"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
        os.replace(tmp, self.path)
        self._cfg = cfg
        self._mtime = os.path.getmtime(self.path)


def cfg_get(cfg: Dict[str, Any], path: str, default=None):
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
