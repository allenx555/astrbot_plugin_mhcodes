import asyncio
import json

import pytest
from astrbot_plugin_mhcodes.storage import (
    MAX_CODE_LENGTH,
    MAX_GROUP_CODES,
    MAX_ROLE_LENGTH,
    MAX_WEAPON_LENGTH,
    InputError,
    group_key,
)
from test_handlers import Event, dispatch


@pytest.mark.parametrize(
    "action,maximum",
    [("role", MAX_ROLE_LENGTH), ("weapon", MAX_WEAPON_LENGTH), ("add", MAX_CODE_LENGTH)],
)
def test_input_limit_accepts_boundary_and_rejects_without_writing(setup_store, action, maximum):
    store, _ = setup_store

    async def scenario():
        key = group_key("qq", "100")
        # 中文按字符计数，首尾空白不占用登记内容长度。
        await store.execute(action, key, " " + "猎" * maximum + " ", "u1")
        before = store.path.read_bytes()
        with pytest.raises(InputError, match=f"最多 {maximum}"):
            await store.execute(action, key, "猎" * (maximum + 1), "u1")
        assert store.path.read_bytes() == before

    asyncio.run(scenario())


def test_concurrent_additions_respect_group_limit_and_duplicates(setup_store):
    store, _ = setup_store

    async def scenario():
        key = group_key("qq", "100")
        for index in range(MAX_GROUP_CODES - 1):
            await store.execute("add", key, str(index), "u1")
        results = await asyncio.gather(
            store.execute("add", key, "last-a", "u1"),
            store.execute("add", key, "last-b", "u2"),
            return_exceptions=True,
        )
        assert sum(result is True for result in results) == 1
        assert sum(isinstance(result, InputError) for result in results) == 1
        before = (await store.execute("entries", key))[0]
        assert await store.execute("add", key, "0", "u2") is False
        assert (await store.execute("entries", key))[0] == before
        assert len(await store.execute("list", key)) == MAX_GROUP_CODES
        await store.execute("remove", key, "0")
        assert await store.execute("add", key, "replacement", "u1") is True
        assert await store.execute("add", group_key("qq", "200"), "other", "u1") is True

    asyncio.run(scenario())


def test_legacy_over_limit_data_can_be_viewed_and_deleted(setup_store):
    store, _ = setup_store
    key = group_key("qq", "100")
    long_code = "old" * MAX_CODE_LENGTH
    records = [
        {"code": long_code if i == 0 else str(i), "registered_at": None, "registered_by": "u1"}
        for i in range(MAX_GROUP_CODES + 1)
    ]
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "last_reset_cycle": "2026-10-11",
                "groups": {
                    key: {
                        "codes": records,
                        "members": {"u1": {"role": "猎" * 100, "weapon": "刀" * 100}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    async def scenario():
        before = store.path.read_bytes()
        snapshot = await store.execute("snapshot", key, sender_id="u1")
        assert len(snapshot["entries"]) == MAX_GROUP_CODES + 1
        assert snapshot["profile"]["role"] == "猎" * 100
        assert store.path.read_bytes() == before
        with pytest.raises(InputError):
            await store.execute("add", key, "new", "u1")
        assert await store.execute("remove", key, long_code) is True
        assert await store.execute("remove_index", key, "1") == "1"
        assert await store.execute("add", key, "new", "u1") is True

    asyncio.run(scenario())


def test_snapshot_reads_once_and_returns_detached_data(setup_store, monkeypatch):
    store, _ = setup_store

    async def scenario():
        key = group_key("qq", "100")
        await store.execute("role", key, "猎人", "u1")
        await store.execute("weapon", key, "太刀", "u1")
        await store.execute("add", key, "ABC", "u1")
        loads = []
        original = store._load

        def counted(cycle):
            loads.append(cycle)
            return original(cycle)

        monkeypatch.setattr(store, "_load", counted)
        snapshot = await store.execute("snapshot", key, sender_id="u1")
        assert len(loads) == 1
        assert snapshot["entries"][0]["role"] == snapshot["profile"]["role"] == "猎人"
        snapshot["profile"]["role"] = "modified"
        snapshot["entries"][0]["code"] = "modified"
        assert await store.execute("profile", key, sender_id="u1") == {
            "role": "猎人",
            "weapon": "太刀",
        }
        assert await store.execute("list", key) == ["ABC"]
        assert await store.execute("snapshot", group_key("qq", "200"), sender_id="u1") == {
            "entries": [],
            "profile": {},
        }

    asyncio.run(scenario())


def test_handler_uses_one_snapshot_and_segments_long_list(plugin_module, monkeypatch):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {})
        await plugin.initialize()
        key = group_key("qq", "100")
        await plugin.store.execute("role", key, "猎人", "user1")
        for i in range(30):
            await plugin.store.execute("add", key, f"CODE-{i:02d}-" + "x" * 100, "user1")
        snapshot = await plugin.store.execute("snapshot", key, sender_id="user1")
        actions = []
        original = plugin.store.execute

        async def counted(action, *args, **kwargs):
            actions.append(action)
            return await original(action, *args, **kwargs)

        monkeypatch.setattr(plugin.store, "execute", counted)
        event = Event("/mh查看集会码")
        replies = await dispatch(plugin, event)
        assert actions == ["snapshot"]
        assert len(replies) > 1
        assert all(0 < len(reply) <= plugin_module.MAX_MESSAGE_LENGTH for reply in replies)
        combined = "".join(replies)
        assert combined.startswith("你的角色：猎人")
        for index, entry in enumerate(snapshot["entries"], 1):
            assert combined.count(plugin._format_entry(index, entry)) == 1
        assert event.stopped and not event.call_llm
        await plugin.terminate()

    asyncio.run(scenario())


def test_handler_reports_input_limit_without_storage_change(plugin_module):
    async def scenario():
        plugin = plugin_module.MhCodesPlugin(None, {})
        await plugin.initialize()
        before = plugin.store.path.read_bytes()
        for command, length in [
            ("角色", MAX_ROLE_LENGTH),
            ("武器", MAX_WEAPON_LENGTH),
            ("添加集会码", MAX_CODE_LENGTH),
        ]:
            event = Event(f"/mh{command} " + "字" * (length + 1))
            reply = (await dispatch(plugin, event))[0]
            assert f"最多 {length}" in reply and "操作失败" not in reply
            assert event.stopped and not event.call_llm
        assert plugin.store.path.read_bytes() == before
        await plugin.terminate()

    asyncio.run(scenario())


@pytest.mark.parametrize("text", ["字" * 3001, ("行\n" * 1600), ("记录\n\n" * 1000), "字" * 1500])
def test_segments_preserve_all_text_including_legacy_long_lines(plugin_module, text):
    chunks = plugin_module.split_message(text)
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= plugin_module.MAX_MESSAGE_LENGTH for chunk in chunks)
