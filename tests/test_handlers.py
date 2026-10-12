import asyncio
import json
from pathlib import Path

import pytest


class Event:
    def __init__(self, text, group="100", platform="qq"):
        self.text, self.group, self.platform = text, group, platform
        self.is_at_or_wake_command = False
        self.stopped = False
        self.call_llm = True

    def get_message_str(self):
        return self.text

    def get_sender_id(self):
        return "user1"

    def get_group_id(self):
        return self.group

    def get_platform_id(self):
        return self.platform

    def should_call_llm(self, value):
        self.call_llm = value

    def plain_result(self, text):
        return text

    def stop_event(self):
        self.stopped = True


async def dispatch(plugin, event):
    handler = plugin.mhcodes
    # 替身仅验证声明和业务入口；不模拟 AstrBot 消息管线。
    if handler.test_message_type != "group" or not event.group:
        return []
    if not handler.test_regex.search(event.text.strip()):
        return []
    return [reply async for reply in handler(event)]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/mh添加集会码 ABC def", ("添加集会码", "ABC def")),
        (" /mh添加集会码 ABC \n def ", ("添加集会码", "ABC \n def")),
        ("/mh添加集会码", ("添加集会码", "")),
        ("/mh删除集会码\tABC", ("删除集会码", "ABC")),
        ("/mh查看集会码", ("查看集会码", "")),
        ("/mh重置集会码", ("重置集会码", "")),
        ("我想查看集会码", None),
        ("/mh查看集会码 其他", None),
        ("/mh添加集会码ABC", None),
        ("/mh角色猎人", None),
        ("/mh武器太刀", None),
        ("/mh删除集会码ABC", None),
        ("/mh删除序号1", None),
        ("/mh 角色 猎人", ("角色", "猎人")),
        ("/mh角色 猎人 名字", ("角色", "猎人 名字")),
        ("/mh重置集会码\n聊天", None),
    ],
)
def test_parser(plugin_module, text, expected):
    assert plugin_module.parse_command(text) == expected


def test_handler_flow_and_private_filter(plugin_module):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {"daily_reset_enabled": False})
        await plugin.initialize()
        event = Event("/mh添加集会码 ABC def")
        assert await dispatch(plugin, event) == ["✅️集会码 ABC def 已添加到当前群组"]
        assert event.stopped and not event.call_llm
        assert "已存在" in (await dispatch(plugin, Event("/mh添加集会码 ABC def")))[0]
        assert "📜当前集会码📜\n1. ABC def" in (await dispatch(plugin, Event("/mh查看集会码")))[0]
        assert (await dispatch(plugin, Event("/mh查看集会码", group="200")))[0].endswith(
            "❌当前没有集会码"
        )
        assert (await dispatch(plugin, Event("/mh查看集会码", platform="qq2")))[0].endswith(
            "❌当前没有集会码"
        )
        assert await dispatch(plugin, Event("/mh重置集会码", group="")) == []
        assert "不能为空" in (await dispatch(plugin, Event("/mh删除集会码")))[0]
        assert "已从当前群组删除" in (await dispatch(plugin, Event("/mh删除集会码 ABC def")))[0]
        assert "不存在" in (await dispatch(plugin, Event("/mh删除集会码 ABC def")))[0]
        await dispatch(plugin, Event("/mh添加集会码 new"))
        assert "已全部重置" in (await dispatch(plugin, Event("/mh重置集会码")))[0]
        assert "没有集会码需要重置" in (await dispatch(plugin, Event("/mh重置集会码")))[0]
        await plugin.terminate()

    asyncio.run(scenario())


def test_corruption_has_user_visible_failure(plugin_module):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {"daily_reset_enabled": False})
        await plugin.initialize()
        plugin.store.path.write_text("broken", encoding="utf-8")
        event = Event("/mh添加集会码 new")
        assert "操作失败" in (await dispatch(plugin, event))[0]
        assert plugin.store.path.read_text(encoding="utf-8") == "broken"
        assert event.stopped and not event.call_llm

    asyncio.run(scenario())


def test_reload_cleans_up_and_initialize_is_idempotent(plugin_module):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {"daily_reset_enabled": True})
        await plugin.initialize()
        first = plugin._reset_task
        await asyncio.sleep(0)
        await plugin.initialize()
        assert plugin._reset_task is first
        await plugin.terminate()
        assert first.cancelled()
        assert plugin._reset_task is None
        await plugin.terminate()
        await plugin.initialize()
        assert plugin._reset_task is not first
        await plugin.terminate()

    asyncio.run(scenario())


def test_schema_defaults_match_runtime():
    from astrbot_plugin_mhcodes.storage import Settings

    schema = json.loads(
        (Path(__file__).parents[1] / "_conf_schema.json").read_text(encoding="utf-8")
    )
    defaults = {key: item["default"] for key, item in schema.items()}
    assert Settings.from_config(defaults) == Settings()
