import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from astrbot_plugin_mhcodes.storage import CodeStore, Settings, StorageError, group_key


def run(coro):
    return asyncio.run(coro)


def test_crud_isolation_and_persistence(setup_store):
    store, clock = setup_store

    async def scenario():
        a, b, c = group_key("qq", "100"), group_key("qq", "200"), group_key("qq2", "100")
        assert await store.execute("add", a, " ABC def ") is True
        assert await store.execute("add", a, "ABC def") is False
        assert await store.execute("add", a, "second") is True
        assert await store.execute("list", b) == []
        assert await store.execute("list", c) == []
        reloaded = CodeStore(store.path, Settings(True), lambda: clock[0])
        assert await reloaded.execute("list", a) == ["ABC def", "second"]
        assert await store.execute("remove", a, "missing") is False
        assert await store.execute("remove", a, "ABC def") is True
        assert await store.execute("list", a) == ["second"]
        assert await store.execute("reset", a) is True
        assert await store.execute("reset", a) is False

    run(scenario())


def test_daily_boundary_recovery_and_no_repeat(setup_store):
    store, clock = setup_store

    async def scenario():
        a, b = group_key("qq", "100"), group_key("qq", "200")
        await store.execute("add", a, "old")
        await store.execute("add", b, "old")
        assert await store.execute("refresh") == 0
        clock[0] += timedelta(seconds=1)
        # 到达 4 点时，命令本身先补清空，然后添加新码。
        assert await store.execute("add", a, "new") is True
        assert await store.execute("list", a) == ["new"]
        assert await store.execute("list", b) == []
        assert await store.execute("refresh") == 0
        reloaded = CodeStore(store.path, Settings(True), lambda: clock[0])
        assert await reloaded.execute("refresh") == 0
        assert await reloaded.execute("list", a) == ["new"]
        clock[0] += timedelta(days=3)
        assert await reloaded.execute("refresh") == 1
        assert await reloaded.execute("list", a) == []

    run(scenario())


def test_disabled_reset_and_backwards_clock(setup_store):
    store, clock = setup_store

    async def scenario():
        key = group_key("qq", "100")
        await store.execute("add", key, "old")
        clock[0] -= timedelta(days=1)
        assert await store.execute("refresh") == 0
        assert await store.execute("list", key) == ["old"]
        clock[0] += timedelta(days=10)
        disabled = CodeStore(store.path, Settings(False), lambda: clock[0])
        assert await disabled.execute("refresh") == 0
        assert await disabled.execute("list", key) == ["old"]

    run(scenario())


def test_concurrent_mutations_do_not_lose_updates(setup_store):
    store, _ = setup_store

    async def scenario():
        key = group_key("qq", "100")
        await asyncio.gather(*(store.execute("add", key, str(i)) for i in range(40)))
        assert set(await store.execute("list", key)) == {str(i) for i in range(40)}
        await asyncio.gather(*(store.execute("remove", key, str(i)) for i in range(20)))
        assert set(await store.execute("list", key)) == {str(i) for i in range(20, 40)}

    run(scenario())


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        "[]",
        '{"groups": {"100": {"codes": ["old"]}}}',
        '{"schema_version": 1, "last_reset_cycle": "invalid", "groups": {}}',
        '{"schema_version": 1, "last_reset_cycle": "2026-10-11", "groups": []}',
        json.dumps(
            {
                "schema_version": 1,
                "last_reset_cycle": "2026-10-11",
                "groups": {group_key("qq", "100"): {"codes": ["duplicate", "duplicate"]}},
            }
        ),
    ],
)
def test_corrupt_or_legacy_data_is_never_overwritten(setup_store, content):
    store, _ = setup_store
    store.path.write_text(content, encoding="utf-8")
    with pytest.raises(StorageError):
        run(store.execute("add", group_key("qq", "100"), "new"))
    assert store.path.read_text(encoding="utf-8") == content


def test_failed_atomic_replace_preserves_original(setup_store, monkeypatch):
    store, _ = setup_store
    key = group_key("qq", "100")
    run(store.execute("add", key, "old"))
    original = store.path.read_bytes()

    def fail(*args):
        raise PermissionError("read only")

    monkeypatch.setattr("astrbot_plugin_mhcodes.storage.os.replace", fail)
    with pytest.raises(StorageError):
        run(store.execute("add", key, "new"))
    assert store.path.read_bytes() == original
    assert not list(store.path.parent.glob("*.tmp"))


def test_cancelled_transaction_finishes_before_next_writer(setup_store, monkeypatch):
    store, _ = setup_store
    entered, release = threading.Event(), threading.Event()
    original = store._transaction

    def blocked(*args):
        if args[2] == "first":
            entered.set()
            assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(store, "_transaction", blocked)

    async def scenario():
        key = group_key("qq", "100")
        first = asyncio.create_task(store.execute("add", key, "first"))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            first.cancel()
            second = asyncio.create_task(store.execute("add", key, "second"))
            await asyncio.sleep(0)
            assert not second.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert await second is True
        assert await store.execute("list", key) == ["first", "second"]

    run(scenario())


@pytest.mark.parametrize("waiter_action", ["add", "close"])
@pytest.mark.parametrize("write_fails", [False, True])
def test_repeated_cancellation_waits_for_write_and_close(
    setup_store, monkeypatch, waiter_action, write_fails
):
    store, _ = setup_store
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = store._save

    def blocked(data):
        if any(
            entry["code"] == "first"
            for group in data["groups"].values()
            for entry in group["codes"]
        ):
            entered.set()
            try:
                assert release.wait(5)
                if write_fails:
                    raise StorageError("simulated write failure")
                original(data)
            finally:
                finished.set()
        else:
            original(data)

    monkeypatch.setattr(store, "_save", blocked)

    async def scenario():
        key = group_key("qq", "100")
        first = asyncio.create_task(store.execute("add", key, "first"))
        waiter = None
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            for _ in range(3):
                first.cancel()
                # 让取消传递到事务等待，并给 worker 的取消回调执行机会。
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                assert not first.done()
            waiter = asyncio.create_task(
                store.execute("add", key, "second") if waiter_action == "add" else store.close()
            )
            await asyncio.sleep(0)
            assert not waiter.done()
            assert not finished.is_set()
        finally:
            release.set()
            # 即使断言失败，也等待线程结束，避免污染后续测试。
            assert await asyncio.to_thread(finished.wait, 5)
            await asyncio.gather(first, return_exceptions=True)
        with pytest.raises(asyncio.CancelledError):
            await first
        assert waiter is not None
        await waiter
        if waiter_action == "close":
            with pytest.raises(StorageError):
                await store.execute("list", key)
            await store.reopen()
        expected = [] if write_fails else ["first"]
        if waiter_action == "add":
            expected.append("second")
        assert await store.execute("list", key) == expected

    run(scenario())


@pytest.mark.parametrize(
    "config",
    [
        {"reset_hour": -1},
        {"reset_hour": 24},
        {"reset_hour": True},
        {"daily_reset_enabled": "false"},
    ],
)
def test_invalid_config_is_rejected(config):
    with pytest.raises(ValueError):
        Settings.from_config(config)


def test_beijing_time_and_custom_hour():
    now = datetime(2026, 10, 11, 19, 59, 59, tzinfo=timezone.utc)
    assert Settings().cycle(now) == "2026-10-11"
    assert Settings().cycle(now + timedelta(seconds=1)) == "2026-10-12"
    assert Settings(reset_hour=0).cycle(now) == "2026-10-12"
    # 旧安装即使残留 timezone 配置，也不影响固定北京时间。
    assert (
        Settings.from_config({"timezone": "UTC"}).cycle(now + timedelta(seconds=1)) == "2026-10-12"
    )
    assert group_key("a:b", "c") != group_key("a", "b:c")


def test_closed_store_rejects_old_handlers(setup_store):
    store, _ = setup_store

    async def scenario():
        key = group_key("qq", "100")
        await store.execute("add", key, "old")
        await store.close()
        with pytest.raises(StorageError):
            await store.execute("add", key, "stale-handler")
        await store.reopen()
        assert await store.execute("list", key) == ["old"]

    run(scenario())
