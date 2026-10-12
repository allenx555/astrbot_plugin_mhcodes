"""真实 AstrBot API 冒烟检查；临时数据目录，不连接消息平台。"""

import asyncio
import json
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


async def check(root):
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.message_components import Plain
    from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType, PlatformMetadata
    from astrbot.api.star import Star
    from astrbot.core.star.filter.event_message_type import EventMessageTypeFilter
    from astrbot.core.star.filter.regex import RegexFilter
    from astrbot.core.star.star import star_map
    from astrbot.core.star.star_manager import PluginManager
    from astrbot_plugin_mhcodes import main

    metadata = PluginManager._load_plugin_metadata(str(root))
    assert metadata.name == "astrbot_plugin_mhcodes"
    # 复现加载器的元数据注入；不启动服务或连接 QQ。
    star_map[main.__name__].name = metadata.name
    plugin = main.MhCodesPlugin(None, {"daily_reset_enabled": True})
    assert isinstance(plugin, Star)
    regex = RegexFilter(main.COMMAND_PATTERN)
    group_filter = EventMessageTypeFilter(filter.EventMessageType.GROUP_MESSAGE)

    def event(text, group="100", platform="qq-test"):
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
        message.self_id = "bot"
        message.group_id = group
        message.session_id = group or "sender"
        message.message_id = "1"
        message.sender = MessageMember(user_id="sender", nickname="Tester")
        message.message = [Plain(text)]
        message.message_str = text
        message.raw_message = {}
        return AstrMessageEvent(
            text, message, PlatformMetadata("aiocqhttp", "test", platform), message.session_id
        )

    async def dispatch(text, group="100", platform="qq-test"):
        text = "/mh" + text.lstrip("/")
        incoming = event(text, group, platform)
        assert incoming.is_at_or_wake_command is False
        if not group_filter.filter(incoming, {}) or not regex.filter(incoming, {}):
            return []
        replies = [reply async for reply in plugin.mhcodes(incoming)]
        assert incoming.is_stopped()
        assert incoming.call_llm is False
        return [reply.chain[0].text for reply in replies]

    await plugin.initialize()
    first_task = plugin._reset_task
    await plugin.initialize()
    assert plugin._reset_task is first_task
    assert "角色：猎人" in (await dispatch("角色 猎人"))[0]
    assert "武器：太刀" in (await dispatch("武器 太刀"))[0]
    assert "已添加" in (await dispatch("添加集会码 ABC def"))[0]
    assert "已存在" in (await dispatch("添加集会码 ABC def"))[0]
    assert "📜当前集会码📜\n1. ABC def" in (await dispatch("查看集会码"))[0]
    view = (await dispatch("查看集会码"))[0]
    assert "角色：猎人 ｜ 武器：太刀" in view and "登记时间：" in view
    assert (await dispatch("查看集会码", group="200"))[0].endswith("❌当前没有集会码")
    assert (await dispatch("查看集会码", platform="qq-test-2"))[0].endswith("❌当前没有集会码")
    assert await dispatch("重置集会码", group="") == []
    assert await dispatch("我想查看集会码") == []
    assert "不能为空" in (await dispatch("删除集会码"))[0]
    assert "已从当前群组删除" in (await dispatch("/删除集会码 ABC def"))[0]
    assert (await dispatch("查看集会码"))[0].endswith("❌当前没有集会码")
    await dispatch("添加集会码 another")
    assert "已全部重置" in (await dispatch("重置集会码"))[0]
    await dispatch("添加集会码 numbered")
    assert "已删除集会码 numbered" in (await dispatch("删除序号 1"))[0]
    await dispatch("添加集会码 persisted")
    await plugin.terminate()
    assert first_task.cancelled()
    plugin = main.MhCodesPlugin(None, {"daily_reset_enabled": True})
    await plugin.initialize()
    assert "📜当前集会码📜\n1. persisted" in (await dispatch("查看集会码"))[0]
    await plugin.terminate()
    print(
        json.dumps(
            {
                "astrbot": version("astrbot"),
                "metadata": "OK",
                "real_api_handlers": "OK",
                "mh_prefix_filters": "OK",
                "role_weapon_timestamp": "OK",
                "private_message_filter": "OK",
                "group_and_platform_isolation": "OK",
                "persistence": "OK",
                "lifecycle_cleanup": "OK",
                "qq_delivery": "NOT_TESTED",
            }
        )
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root.parent))
    # 在导入 AstrBot 之前切换目录，框架产生的数据库/日志均位于临时目录。
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="mhcodes-astrbot-") as temp:
        try:
            os.chdir(temp)
            asyncio.run(check(root))
        finally:
            os.chdir(original_cwd)
