"""群集会码存储：异步串行事务、原子写入和跨日补重置。"""

import asyncio
import json
import os
import tempfile
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BEIJING_TIME = timezone(timedelta(hours=8), "北京时间")


class StorageError(Exception):
    """无法安全读取或写入数据；原文件不会被当成空数据覆盖。"""


@dataclass(frozen=True)
class Settings:
    daily_reset_enabled: bool = False
    reset_hour: int = 4

    @classmethod
    def from_config(cls, config: Mapping):
        enabled = config.get("daily_reset_enabled", False)
        hour = config.get("reset_hour", 4)
        if type(enabled) is not bool:
            raise ValueError("daily_reset_enabled 必须是布尔值")
        if type(hour) is not int or not 0 <= hour <= 23:
            raise ValueError("reset_hour 必须是 0 到 23 的整数")
        return cls(enabled, hour)

    def cycle(self, now: datetime) -> str:
        """以当地重置时刻为每天的边界，而不是以午夜为边界。"""
        if now.tzinfo is None:
            raise ValueError("时间必须包含时区")
        local = now.astimezone(BEIJING_TIME)
        day = local.date()
        if local.hour < self.reset_hour:
            day -= timedelta(days=1)
        return day.isoformat()


def group_key(platform_id: str, group_id: str) -> str:
    """JSON 数组编码避免平台 ID 或群 ID 中的分隔符发生碰撞。"""
    if not platform_id or not group_id:
        raise ValueError("平台实例 ID 和群 ID 不能为空")
    return json.dumps([str(platform_id), str(group_id)], ensure_ascii=False)


class CodeStore:
    def __init__(
        self,
        path: Path,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
    ):
        self.path = path
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = asyncio.Lock()
        self._closed = False

    async def reopen(self) -> None:
        async with self._lock:
            self._closed = False

    async def close(self) -> None:
        """等待正在执行的写入结束，拒绝旧实例的后续事务。"""
        async with self._lock:
            self._closed = True

    def _load(self, cycle: str) -> tuple[dict, bool]:
        try:
            content = self.path.read_text(encoding="utf-8")
            data = json.loads(content)
            if (
                isinstance(data, dict)
                and type(data.get("schema_version")) is int
                and data["schema_version"] == 1
            ):
                self._validate_legacy(data)
                # 自动升级前保存原文件。旧记录的时间和登记人未知，不能编造。
                backup = self.path.with_name(f"{self.path.name}.v1.{uuid.uuid4().hex}.bak")
                with backup.open("x", encoding="utf-8") as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                for group in data["groups"].values():
                    group["codes"] = [
                        {"code": code, "registered_at": None, "registered_by": ""}
                        for code in group["codes"]
                    ]
                    group["members"] = {}
                data["schema_version"] = 2
                return data, True
            self._validate(data)
            return data, False
        except FileNotFoundError:
            return {"schema_version": 2, "last_reset_cycle": cycle, "groups": {}}, True
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError(f"集会码数据读取失败，原文件已保留: {exc}") from exc

    @staticmethod
    def _validate_legacy(data: dict) -> None:
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
        ):
            raise ValueError("未知数据版本，不能直接使用 NoneBot 原始 JSON")
        cycle = data.get("last_reset_cycle")
        if not isinstance(cycle, str) or date.fromisoformat(cycle).isoformat() != cycle:
            raise ValueError("重置日期无效")
        groups = data.get("groups")
        if not isinstance(groups, dict):
            raise ValueError("groups 必须是对象")
        for key, group in groups.items():
            ids = json.loads(key)
            if (
                not isinstance(ids, list)
                or len(ids) != 2
                or any(not isinstance(value, str) or not value for value in ids)
                or not isinstance(group, dict)
                or not isinstance(group.get("codes"), list)
                or any(not isinstance(code, str) or not code.strip() for code in group["codes"])
                or len(set(group["codes"])) != len(group["codes"])
            ):
                raise ValueError("群数据格式无效")

    @staticmethod
    def _validate(data: dict) -> None:
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 2
        ):
            raise ValueError("未知数据版本")
        cycle = data.get("last_reset_cycle")
        if not isinstance(cycle, str) or date.fromisoformat(cycle).isoformat() != cycle:
            raise ValueError("重置日期无效")
        if not isinstance(data.get("groups"), dict):
            raise ValueError("groups 必须是对象")
        for key, group in data["groups"].items():
            ids = json.loads(key)
            if (
                not isinstance(ids, list)
                or len(ids) != 2
                or any(not isinstance(v, str) or not v for v in ids)
            ):
                raise ValueError("群数据键无效")
            if (
                not isinstance(group, dict)
                or not isinstance(group.get("codes"), list)
                or not isinstance(group.get("members"), dict)
            ):
                raise ValueError("群数据格式无效")
            seen = set()
            for entry in group["codes"]:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("code"), str)
                    or not entry["code"].strip()
                    or entry["code"] in seen
                ):
                    raise ValueError("集会码记录无效")
                seen.add(entry["code"])
                if not isinstance(entry.get("registered_by"), str) or "registered_at" not in entry:
                    raise ValueError("登记信息无效")
                if entry["registered_at"] is not None:
                    stamp = datetime.fromisoformat(entry["registered_at"])
                    if stamp.tzinfo is None:
                        raise ValueError("登记时间缺少时区")
            for uid, profile in group["members"].items():
                if (
                    not uid
                    or not isinstance(profile, dict)
                    or any(not isinstance(profile.get(field), str) for field in ("role", "weapon"))
                ):
                    raise ValueError("角色资料无效")

    def _save(self, data: dict) -> None:
        temp_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, suffix=".tmp", delete=False
            ) as file:
                temp_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise StorageError(f"集会码数据保存失败: {exc}") from exc
        finally:
            if temp_path is not None:
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)

    def _transaction(self, action: str, key: str | None, code: str, now: datetime, sender_id: str):
        cycle = self.settings.cycle(now)
        data, changed = self._load(cycle)
        reset_count = 0
        if self.settings.daily_reset_enabled and data["last_reset_cycle"] < cycle:
            for group in data["groups"].values():
                if group["codes"]:
                    group["codes"] = []
                    reset_count += 1
            data["last_reset_cycle"] = cycle
            changed = True

        codes = data["groups"].get(key, {}).get("codes", [])
        existing = next((entry for entry in codes if entry["code"] == code), None)
        result = False
        if action == "add" and existing is None:
            data["groups"].setdefault(key, {"codes": [], "members": {}})["codes"].append(
                {
                    "code": code,
                    "registered_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                    "registered_by": sender_id,
                }
            )
            changed = result = True
        elif action == "remove" and existing is not None:
            codes.remove(existing)
            changed = result = True
        elif action == "remove_index":
            index = int(code) - 1
            if 0 <= index < len(codes):
                result = codes.pop(index)["code"]
                changed = True
        elif action == "reset" and codes:
            data["groups"][key]["codes"] = []
            changed = result = True
        elif action == "list":
            result = [entry["code"] for entry in codes]
        elif action == "entries":
            members = data["groups"].get(key, {}).get("members", {})
            result = [{**entry, **members.get(entry["registered_by"], {})} for entry in codes]
        elif action in {"role", "weapon"}:
            group = data["groups"].setdefault(key, {"codes": [], "members": {}})
            profile = group["members"].setdefault(sender_id, {"role": "", "weapon": ""})
            profile[action] = code
            changed = result = True
        elif action == "profile":
            result = dict(data["groups"].get(key, {}).get("members", {}).get(sender_id, {}))
        elif action == "refresh":
            result = reset_count
        if changed:
            self._save(data)
        return result

    async def execute(
        self, action: str, key: str | None = None, code: str = "", sender_id: str = ""
    ):
        if action not in {
            "add",
            "remove",
            "reset",
            "list",
            "entries",
            "remove_index",
            "role",
            "weapon",
            "profile",
            "refresh",
        }:
            raise ValueError("未知操作")
        if action != "refresh" and not key:
            raise ValueError("群数据键不能为空")
        if action in {"role", "weapon"} and not sender_id:
            raise ValueError("登记用户不能为空")
        if action == "remove_index" and (not code.isdecimal() or int(code) < 1):
            raise ValueError("序号必须是正整数")
        if action in {"add", "remove", "role", "weapon"}:
            code = code.strip()
            if not code:
                raise ValueError("集会码不能为空")
        async with self._lock:
            if self._closed:
                raise StorageError("插件已停用或正在重载，请稍后重试")
            # 取消 to_thread 的 await 不会停止线程。等事务结束再释放锁，
            # 保证重载取消任务时不会出现两个写入者或半完成的事务。
            worker = asyncio.create_task(
                asyncio.to_thread(self._transaction, action, key, code, self.clock(), sender_id)
            )
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                try:
                    await worker
                finally:
                    raise
