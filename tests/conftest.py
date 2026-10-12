"""入口单元测试使用 API 替身；不代表真实 AstrBot 加载或 QQ 收发验证。"""

import importlib.util
import logging
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def setup_store(tmp_path):
    from datetime import datetime, timezone

    from astrbot_plugin_mhcodes.storage import CodeStore, Settings

    clock = [datetime(2026, 10, 11, 19, 59, 59, tzinfo=timezone.utc)]
    store = CodeStore(tmp_path / "codes.json", Settings(True), lambda: clock[0])
    return store, clock


@pytest.fixture
def plugin_module(monkeypatch, tmp_path):
    def decorate(name, value):
        def decorator(func):
            setattr(func, name, value)
            return func

        return decorator

    class Star:
        def __init__(self, context):
            self.context = context

    api = ModuleType("astrbot.api")
    api.AstrBotConfig = dict
    api.logger = logging.getLogger("test-mhcodes")
    event_api = ModuleType("astrbot.api.event")
    event_api.AstrMessageEvent = object
    event_api.filter = SimpleNamespace(
        regex=lambda pattern: decorate("test_regex", re.compile(pattern)),
        event_message_type=lambda value: decorate("test_message_type", value),
        EventMessageType=SimpleNamespace(GROUP_MESSAGE="group"),
    )
    star_api = ModuleType("astrbot.api.star")
    star_api.Star = Star
    star_api.Context = object
    star_api.StarTools = SimpleNamespace(get_data_dir=lambda: tmp_path)
    for name, module in {
        "astrbot": ModuleType("astrbot"),
        "astrbot.api": api,
        "astrbot.api.event": event_api,
        "astrbot.api.star": star_api,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "astrbot_plugin_mhcodes._test_main"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "main.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module
