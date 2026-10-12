"""在临时实例中验证真实插件加载、唤醒管线与重载；不启动平台或模型服务。"""

import asyncio
import json
import os
import sys
import tempfile
import zipfile
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

from build_package import build_package


async def check(name: str, root: Path) -> dict:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.message_components import Plain
    from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType, PlatformMetadata
    from astrbot.api.star import Context
    from astrbot.core import astrbot_config, db_helper, sp
    from astrbot.core.pipeline.process_stage.stage import StarRequestSubStage
    from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
    from astrbot.core.star.star import star_registry
    from astrbot.core.star.star_handler import star_handlers_registry
    from astrbot.core.star.star_manager import PluginManager

    # 插件所需的 Context 方法使用真实实现；不初始化无关的平台/模型管理器。
    context = Context.__new__(Context)
    manager = PluginManager(context, astrbot_config)
    manager.reserved_plugin_path = str(root / "empty-builtins")
    await asyncio.to_thread(Path(manager.plugin_config_path).mkdir, parents=True, exist_ok=True)
    astrbot_config["wake_prefix"] = ["/"]
    astrbot_config["plugin_set"] = [name]
    pipeline_context = SimpleNamespace(
        astrbot_config=astrbot_config,
        plugin_manager=manager,
        astrbot_config_id="lifecycle-smoke",
        db_helper=None,  # 跳过与插件无关的会话自动命名后台服务。
    )
    waking = WakingCheckStage()
    calling = StarRequestSubStage()
    await waking.initialize(pipeline_context)
    await calling.initialize(pipeline_context)

    def event(text, group="100", sender="u1"):
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
        message.self_id, message.group_id, message.session_id = "bot", group, group or sender
        message.message_id = "smoke"
        message.sender = MessageMember(user_id=sender, nickname="Tester")
        message.message, message.message_str = [Plain(text)], text
        message.raw_message = {}
        return AstrMessageEvent(
            text, message, PlatformMetadata("aiocqhttp", "test", "test"), message.session_id
        )

    async def dispatch(text, **kwargs):
        incoming = event(text, **kwargs)
        await waking.process(incoming)
        replies = []
        if not incoming.is_stopped() and incoming.get_extra("activated_handlers"):
            async for _ in calling.process(incoming):
                result = incoming.get_result()
                if result:
                    replies.append(
                        "".join(part.text for part in result.chain if isinstance(part, Plain))
                    )
        return replies, incoming

    def metadata():
        matches = [item for item in star_registry if item.name == name]
        assert len(matches) == 1, "加载器没有注册且仅注册一个插件"
        return matches[0]

    try:
        success, error = await manager.load(specified_dir_name=name)
        assert success, error
        md = metadata()
        plugin = md.star_cls
        assert plugin is not None and plugin.settings.daily_reset_enabled is False
        assert plugin.store.path == root / "data" / "plugin_data" / name / "mh_codes.json"
        assert len(star_handlers_registry.get_handlers_by_module_name(md.module_path)) == 1
        assert md.config["reset_hour"] == 4
        assert await asyncio.to_thread(Path(md.config.config_path).is_file)

        replies, incoming = await dispatch("/mh角色 猎人")
        assert "角色：猎人" in replies[0]
        assert incoming.message_str == "mh角色 猎人" and incoming.is_at_or_wake_command
        assert "武器：太刀" in (await dispatch("/mh 武器 太刀"))[0][0]
        assert "已添加" in (await dispatch("/mh添加集会码 ABC123"))[0][0]
        assert "未登记" in (await dispatch("/mh查看集会码", sender="u2"))[0][0].splitlines()[0]
        assert "角色：猎人 ｜ 武器：太刀" in (await dispatch("/mh查看集会码"))[0][0]
        for text in ("/mh角色猎人", "我想查看集会码", "i猎人", "/w太刀", "mh武器 大剑"):
            assert (await dispatch(text))[0] == [], text
        assert (await dispatch("/mh重置集会码", group=""))[0] == []

        # 非默认唤醒前缀下，带 /mh 的群聊正则入口仍可直接工作。
        astrbot_config["wake_prefix"] = ["!"]
        replies, incoming = await dispatch("/mh查看集会码")
        assert "ABC123" in replies[0] and not incoming.is_at_or_wake_command
        astrbot_config["wake_prefix"] = ["/"]
        astrbot_config["plugin_set"] = []
        assert (await dispatch("/mh查看集会码"))[0] == []
        astrbot_config["plugin_set"] = [name]
        umo = event("/mh查看集会码").unified_msg_origin
        await sp.session_put(umo, "session_plugin_config", {umo: {"disabled_plugins": [name]}})
        assert (await dispatch("/mh查看集会码"))[0] == []
        await sp.session_remove(umo, "session_plugin_config")

        # 经真实配置文件与加载器开启后台任务，再重复重载。
        md.config["daily_reset_enabled"] = True
        md.config.save_config()
        for _ in range(3):
            old = metadata().star_cls
            old_task = old._reset_task
            success, error = await manager.reload(name)
            assert success, error
            current = metadata()
            assert current.star_cls is not old
            assert old.store._closed
            if old_task is not None:
                assert old_task.cancelled()
            try:
                await old.store.execute("list", '["test", "100"]')
            except Exception as exc:
                assert type(exc).__name__ == "StorageError"
            else:
                raise AssertionError("旧插件实例仍接受事务")
            assert len(star_handlers_registry.get_handlers_by_module_name(current.module_path)) == 1
            tasks = [
                task
                for task in asyncio.all_tasks()
                if task.get_name() == "mhcodes-daily-reset" and not task.done()
            ]
            assert len(tasks) == 1
            replies, _ = await dispatch("/mh查看集会码")
            assert "ABC123" in replies[0] and "角色：猎人" in replies[0]
        final_task = metadata().star_cls._reset_task
        await manager.turn_off_plugin(name)
        assert final_task.cancelled() and not metadata().activated
        assert (await dispatch("/mh查看集会码"))[0] == []
        await manager.turn_on_plugin(name)
        assert metadata().activated
        assert "ABC123" in (await dispatch("/mh查看集会码"))[0][0]
        return {
            "astrbot": version("astrbot"),
            "package_loader_and_config": "OK",
            "waking_and_registered_handler_pipeline": "OK",
            "private_and_disabled_plugin_filters": "OK",
            "reload_registry_persistence_and_task_cleanup": "OK",
            "disable_and_enable": "OK",
            "qq_delivery": "NOT_TESTED",
        }
    finally:
        try:
            loaded = context.get_registered_star(name)
            if loaded and loaded.activated:
                await manager.turn_off_plugin(name)
        finally:
            # Windows 下必须先释放 SQLite 连接才能清理临时实例目录。
            await db_helper.engine.dispose()


if __name__ == "__main__":
    manifest = build_package(Path(__file__).resolve().parents[1])
    original_cwd = Path.cwd()
    original_root = os.environ.get("ASTRBOT_ROOT")
    original_reload = os.environ.get("ASTRBOT_RELOAD")
    with tempfile.TemporaryDirectory(prefix="mhcodes-lifecycle-") as temp:
        root = Path(temp).resolve()
        try:
            os.environ["ASTRBOT_ROOT"] = str(root)
            os.environ["ASTRBOT_RELOAD"] = "0"
            os.chdir(root)
            sys.path.insert(0, str(root))
            with zipfile.ZipFile(manifest["path"]) as archive:
                archive.extractall(root / "data" / "plugins")
            print(json.dumps(asyncio.run(check(manifest["name"], root))))
        finally:
            os.chdir(original_cwd)
            for key, previous in (
                ("ASTRBOT_ROOT", original_root),
                ("ASTRBOT_RELOAD", original_reload),
            ):
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
