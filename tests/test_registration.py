import asyncio
import json
from datetime import timedelta

from astrbot_plugin_mhcodes.storage import CodeStore, Settings, group_key
from test_handlers import Event, dispatch


def test_profiles_timestamp_and_duplicate_do_not_refresh(setup_store):
    store, clock = setup_store

    async def scenario():
        key = group_key("qq", "100")
        await store.execute("role", key, "猎人", "u1")
        await store.execute("weapon", key, "太刀", "u1")
        await store.execute("add", key, "ABC", "u1")
        entry = (await store.execute("entries", key))[0]
        assert entry == {
            "code": "ABC",
            "registered_by": "u1",
            "registered_at": "2026-10-11T19:59:59+00:00",
            "role": "猎人",
            "weapon": "太刀",
        }
        clock[0] += timedelta(seconds=0.5)
        assert await store.execute("add", key, "ABC", "u2") is False
        assert (await store.execute("entries", key))[0] == entry
        await store.execute("weapon", key, "盾斧", "u1")
        assert (await store.execute("entries", key))[0]["weapon"] == "盾斧"
        assert await store.execute("profile", key, sender_id="u2") == {}
        assert await store.execute("profile", group_key("qq", "200"), sender_id="u1") == {}
        clock[0] += timedelta(seconds=1)
        assert await store.execute("refresh") == 1
        assert await store.execute("profile", key, sender_id="u1") == {
            "role": "猎人",
            "weapon": "盾斧",
        }
        await store.execute("add", key, "next", "u1")
        await store.execute("reset", key)
        assert await store.execute("profile", key, sender_id="u1") == {
            "role": "猎人",
            "weapon": "盾斧",
        }

    asyncio.run(scenario())


def test_upgrade_v1_preserves_backup_and_unknown_time(setup_store):
    store, clock = setup_store
    key = group_key("qq", "100")
    content = json.dumps(
        {"schema_version": 1, "last_reset_cycle": "2026-10-11", "groups": {key: {"codes": ["old"]}}}
    )
    store.path.write_text(content, encoding="utf-8")

    async def scenario():
        entries = await store.execute("entries", key)
        assert entries == [{"code": "old", "registered_at": None, "registered_by": ""}]
        assert json.loads(store.path.read_text(encoding="utf-8"))["schema_version"] == 2
        backups = list(store.path.parent.glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == content
        reloaded = CodeStore(store.path, Settings(True), lambda: clock[0])
        assert await reloaded.execute("entries", key) == entries
        assert len(list(store.path.parent.glob("*.bak"))) == 1

    asyncio.run(scenario())


def test_chinese_prefix_registration_display_and_number_deletion(plugin_module):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {})
        await plugin.initialize()
        assert "角色：猎人" in (await dispatch(plugin, Event("/mh角色 猎人")))[0]
        assert "武器：太刀" in (await dispatch(plugin, Event("/mh武器 太刀")))[0]
        empty = (await dispatch(plugin, Event("/mh查看集会码")))[0]
        assert "猎人" in empty and "太刀" in empty and "当前没有集会码" in empty
        await dispatch(plugin, Event("/mh添加集会码 ABC"))
        view = (await dispatch(plugin, Event("/mh查看集会码")))[0]
        assert "登记人：user1" in view and "登记时间：" in view and "+0800" in view
        assert "角色：猎人 ｜ 武器：太刀" in view
        assert "已删除集会码 ABC" in (await dispatch(plugin, Event("/mh删除序号 1")))[0]
        assert "该序号不存在" in (await dispatch(plugin, Event("/mh删除序号 9")))[0]
        assert "正整数" in (await dispatch(plugin, Event("/mh删除序号 0")))[0]
        assert "不能为空" in (await dispatch(plugin, Event("/mh角色")))[0]
        assert "/mh武器 太刀" in (await dispatch(plugin, Event("/mh帮助")))[0]
        assert await dispatch(plugin, Event("i猎人")) == []
        assert await dispatch(plugin, Event("/w太刀")) == []
        assert await dispatch(plugin, Event("添加集会码ABC")) == []
        assert await dispatch(plugin, Event("mh武器 大剑")) == []
        stripped = Event("mh武器 大剑")
        stripped.is_at_or_wake_command = True
        assert "武器：大剑" in (await dispatch(plugin, stripped))[0]
        await plugin.terminate()

    asyncio.run(scenario())


def test_default_no_reset_preserves_codes_after_days(tmp_path):
    from datetime import datetime, timezone

    clock = [datetime(2026, 10, 12, tzinfo=timezone.utc)]
    store = CodeStore(tmp_path / "codes.json", Settings(), lambda: clock[0])

    async def scenario():
        key = group_key("qq", "100")
        await store.execute("add", key, "ABC", "u1")
        clock[0] += timedelta(days=5)
        assert await store.execute("refresh") == 0
        assert await store.execute("list", key) == ["ABC"]

    asyncio.run(scenario())
