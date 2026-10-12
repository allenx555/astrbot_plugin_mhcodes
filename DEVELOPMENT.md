# 开发依据与约束

核对日期：2026-10-12。优先使用当前官方指南，不沿用旧版要求必须 `@register` 的说明。

## 可用脚手架与配置

1. [官方入门指南](https://docs.astrbot.app/dev/star/plugin-new.html) 链接的模板为
   [Soulter/helloworld](https://github.com/Soulter/helloworld)，可使用 GitHub 的 `Use this template`。
2. [官方 CLI 文档](https://docs.astrbot.app/en/use/cli.html) 提供 `astrbot plug new <NAME>`，
   会询问作者、描述、版本和仓库 URL。`astrbot init` 初始化的是 AstrBot 实例，不是插件模板。
   `astrbot run --reload` 可在独立开发实例中自动重载插件。
3. [配置指南](https://docs.astrbot.app/dev/star/guides/plugin-config.html)：根目录
   `_conf_schema.json` 定义表单，AstrBot 自动生成
   `data/config/<plugin_name>_config.json`，并向插件构造函数传入 `AstrBotConfig`。
   本版采用 bool 与 int 两个配置项，无需自建设置页面。时间固定为北京时间（UTC+8）。
4. [存储指南](https://docs.astrbot.app/dev/star/guides/storage.html) 提供 >=4.9.2 的
   插件级 KV。也支持 `data/plugin_data/<plugin_name>` 文件存储。本版选择 JSON 便于备份、检查；
   通过公开 `StarTools.get_data_dir()` 获取目录。

## 实际采用的开发约束

- 插件入口为 `main.py`，类继承 `Star`，元数据放在 `metadata.yaml`；不使用已弃用的 `@register`。
- 处理器定义于插件类内，参数为 `self`、`event: AstrMessageEvent`，使用 `yield event.plain_result` 回复。
- 使用 `from astrbot.api import logger` 和 `from astrbot.api.event import filter`。
- 用 `initialize()` 启动后台任务，用 `terminate()` 取消并等待任务退出，以兼容禁用和热重载。
- 数据存放在插件源码目录外；文件读写通过 `asyncio.to_thread`，同一实例用锁保护完整读改写事务。
- 不使用阻塞网络库、阻塞睡眠或 NoneBot 依赖。本插件没有网络请求。
- 配置做运行时校验；文件损坏和保存失败提供日志及用户可见错误。
- 进行相关功能测试与 Ruff 检查/格式化。
- README 标明移植来源，保留原 MIT 许可证。没有复制官方 helloworld 模板的实现代码。
- 元数据更新源为真实移植版仓库 `allenx555/astrbot_plugin_mhcodes`；市场发布仍需实际平台测试。

以上入口及处理器依据 [最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)，
测试、数据目录、异步网络、格式化和移植署名依据
[开发原则](https://docs.astrbot.app/dev/star/plugin-new.html#开发原则)。

## 官方源码交叉核对

除文档外，检查了 AstrBot `v4.16.0` 的源码作为最低 API 基线：

- [Star 生命周期](https://github.com/AstrBotDevs/AstrBot/blob/v4.16.0/astrbot/core/star/__init__.py)
- [数据目录工具](https://github.com/AstrBotDevs/AstrBot/blob/v4.16.0/astrbot/core/star/star_tools.py)
- [消息事件](https://github.com/AstrBotDevs/AstrBot/blob/v4.16.0/astrbot/core/platform/astr_message_event.py)
- [正则过滤器](https://github.com/AstrBotDevs/AstrBot/blob/v4.16.0/astrbot/core/star/filter/regex.py)
- [Python 版本要求](https://github.com/AstrBotDevs/AstrBot/blob/v4.16.0/pyproject.toml)

正则过滤器不受唤醒前缀限制；标准命令会检查唤醒状态，因此不能仅替换装饰器就保证裸命令行为。
插件代码语法目标为 Python 3.10，但所声明的 AstrBot 版本本体要求 Python >=3.12。

## 验证记录

1.1.2 本地功能测试：**42 passed**，覆盖存储、参数空格分隔、命令入口、配置、固定北京时间、角色/武器/时间、编号删除、旧版备份升级和生命周期。
`ruff check .` 与 `ruff format --check .` 在交付前执行。

另使用 uv 隔离安装 AstrBot **4.16.0**（Python 3.12），执行真实 API 冒烟脚本：

```powershell
uv run --no-project --python 3.12 --with "astrbot==4.16.0" --with pytest --with ruff --with pyyaml python scripts/smoke_astrbot.py
```

通过项：官方元数据解析器读取元数据、真实 Star 继承与入口导入、真实消息事件及结果构造、
官方正则和群聊过滤器、/mh 中文命令、角色/武器/登记时间、编号删除、私聊排除、群/平台隔离、持久化重载、重复初始化与任务取消。
脚本只模拟加载器的元数据注入，未启动完整 AstrBot 服务；框架导入时有 MCP 可选能力兼容警告，
本插件不使用 MCP，以上插件相关断言均通过。不能据此声称完整框架服务所有功能正常。

尚未部署到用户的 AstrBot 服务，尚未验证实际 QQ 收发。以上不包含生产数据迁移。
安装包由 `scripts/build_package.py` 的文件清单生成，排除本地测试日志、数据、缓存，并检查 ZIP 完整性。
