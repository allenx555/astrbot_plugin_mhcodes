"""AstrBot 群聊集会登记入口。"""

import asyncio
import re
from contextlib import suppress
from datetime import datetime

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .storage import BEIJING_TIME, CodeStore, Settings, StorageError, group_key

COMMAND_PATTERN = (
    r"^/?mh[ \t]*(角色|武器|添加集会码|删除集会码|删除序号)(?:[ \t]+([\s\S]*))?$"
    r"|^/?mh[ \t]*(查看集会码|重置集会码|帮助)$"
)


def parse_command(message: str) -> tuple[str, str] | None:
    if not message.strip().startswith("/mh"):
        return None
    match = re.fullmatch(COMMAND_PATTERN, message.strip())
    if not match:
        return None
    return match.group(1) or match.group(3), (match.group(2) or "").strip()


class MhCodesPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.settings = Settings.from_config(config)
        self.store = CodeStore(StarTools.get_data_dir() / "mh_codes.json", self.settings)
        self._reset_task: asyncio.Task | None = None

    async def initialize(self):
        """加载数据并补重置；初始化不能重复创建后台任务。"""
        await self.store.reopen()
        count = await self.store.execute("refresh")
        if count:
            logger.info(f"集会码启动补重置完成，清空 {count} 个群")
        if self.settings.daily_reset_enabled and (
            self._reset_task is None or self._reset_task.done()
        ):
            self._reset_task = asyncio.create_task(self._daily_reset(), name="mhcodes-daily-reset")
        logger.info("怪物猎人集会码插件已初始化")

    async def _daily_reset(self):
        """每分钟检查日期；命令事务也会在操作前补重置。"""
        while True:
            await asyncio.sleep(60)
            try:
                count = await self.store.execute("refresh")
                if count:
                    logger.info(f"每日集会码重置完成，清空 {count} 个群")
            except StorageError as exc:
                logger.error(f"每日集会码重置失败，将在下一次检查重试: {exc}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.regex(COMMAND_PATTERN)
    async def mhcodes(self, event: AstrMessageEvent):
        """通过 /mh 登记角色、武器，管理本群集会码。"""
        message = event.get_message_str().strip()
        if message.startswith("mh") and event.is_at_or_wake_command:
            message = "/" + message
        parsed = parse_command(message)
        if parsed is None:
            return
        command, code = parsed
        event.should_call_llm(False)
        # 在结果交给框架后停止传播，避免同一消息再次触发其他处理器。
        try:
            if command == "帮助":
                text = (
                    "/mh角色 猎人\n/mh武器 太刀\n/mh添加集会码 ABC123\n"
                    "/mh查看集会码\n/mh删除集会码 ABC123\n/mh删除序号 1\n/mh重置集会码\n"
                    "登记信息按本群用户保存；查看时显示登记时间。"
                )
            elif command in {"角色", "武器", "添加集会码", "删除集会码"} and not code:
                field = "集会码" if command in {"添加集会码", "删除集会码"} else command
                text = f"❌{field}不能为空，例如 /mh{command} 内容"
            else:
                key = group_key(event.get_platform_id(), event.get_group_id())
                if command in {"角色", "武器"}:
                    await self.store.execute(
                        "role" if command == "角色" else "weapon", key, code, event.get_sender_id()
                    )
                    text = f"✅️已登记你的{command}：{code}"
                elif command == "添加集会码":
                    added = await self.store.execute("add", key, code, event.get_sender_id())
                    text = (
                        f"✅️集会码 {code} 已添加到当前群组"
                        if added
                        else f"✅️集会码 {code} 已存在于当前群组"
                    )
                elif command == "删除集会码":
                    removed = await self.store.execute("remove", key, code)
                    text = (
                        f"✅️集会码 {code} 已从当前群组删除"
                        if removed
                        else f"✅️集会码 {code} 不存在于当前群组"
                    )
                elif command == "删除序号":
                    if not code.isdecimal() or int(code) < 1:
                        text = "❌请输入正整数序号，例如 /mh删除序号 1"
                    else:
                        removed = await self.store.execute("remove_index", key, code)
                        text = (
                            f"✅️已删除集会码 {removed}"
                            if removed
                            else "❌该序号不存在，请重新查看集会码"
                        )
                elif command == "查看集会码":
                    codes = await self.store.execute("entries", key)
                    profile = await self.store.execute(
                        "profile", key, sender_id=event.get_sender_id()
                    )
                    personal = (
                        f"你的角色：{profile.get('role') or '未登记'} ｜ "
                        f"常用武器：{profile.get('weapon') or '未登记'}\n"
                    )
                    text = (
                        personal
                        + "📜当前集会码📜\n"
                        + "\n\n".join(
                            self._format_entry(i, item) for i, item in enumerate(codes, 1)
                        )
                        if codes
                        else personal + "❌当前没有集会码"
                    )
                else:
                    cleared = await self.store.execute("reset", key)
                    text = (
                        "✅️当前群组的集会码已全部重置"
                        if cleared
                        else "❌当前群组没有集会码需要重置"
                    )
        except (StorageError, ValueError) as exc:
            logger.error(f"集会码命令执行失败: {exc}")
            text = "❌集会码操作失败，请联系管理员检查插件日志。"
        yield event.plain_result(text)
        event.stop_event()

    def _format_entry(self, index: int, entry: dict) -> str:
        stamp = entry["registered_at"]
        registered = (
            datetime.fromisoformat(stamp).astimezone(BEIJING_TIME).strftime("%Y-%m-%d %H:%M:%S %z")
            if stamp
            else "未知（旧版记录）"
        )
        return (
            f"{index}. {entry['code']}\n"
            f"角色：{entry.get('role') or '未登记'} ｜ 武器：{entry.get('weapon') or '未登记'}\n"
            f"登记人：{entry['registered_by'] or '未知'}\n"
            f"登记时间：{registered}"
        )

    async def terminate(self):
        """禁用、卸载或热重载时清理后台任务。"""
        if self._reset_task is not None:
            self._reset_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reset_task
            self._reset_task = None
        await self.store.close()
