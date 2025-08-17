from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
import tomllib
import os
import random


class PollingCfg(BaseModel):
    min_seconds: int = 30
    max_seconds: int = 60
    end_grace_seconds: int = 60


class NetworkCfg(BaseModel):
    rotate_user_agents: bool = True
    use_proxies: bool = False
    proxy_file: str = "proxies.txt"
    retry_backoff_seconds: int = 10


class ItemCfg(BaseModel):
    url: str
    site: str


class Settings(BaseModel):
    polling: PollingCfg = PollingCfg()
    network: NetworkCfg = NetworkCfg()
    item: List[ItemCfg] = Field(default_factory=list)

    # ---- helpers -----------------------------------------------------
    _UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]

    def random_headers(self) -> dict[str, str]:
        ua = random.choice(self._UA_POOL)
        return {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
        }

    def random_proxy(self) -> Optional[str]:
        if not self.network.use_proxies:
            return None
        lines = Path(self.network.proxy_file).read_text().splitlines()
        return random.choice(lines).strip()


def load_settings() -> Settings:
    cfg_path = Path(os.getenv("SNIPR_CONFIG", "snipr.toml"))
    raw = tomllib.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    return Settings.model_validate(raw)
