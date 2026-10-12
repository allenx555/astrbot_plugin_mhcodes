# 🎮 怪物猎人集会码插件（astrbot_plugin_mhcodes）

<div align="center">

**在群聊中管理集会码，登记角色与常用武器，查看登记时间**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/allenx555/astrbot_plugin_mhcodes/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/allenx555/astrbot_plugin_mhcodes/actions/workflows/ci.yml)
![Python Version](https://img.shields.io/badge/Python-%3E%3D3.12-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16%2C%3C5-green)
![Adapter](https://img.shields.io/badge/Adapter-aiocqhttp-lightgrey)

</div>

本插件开源免费，欢迎提交 Issue 和 PR。

移植自 [padoru233/nonebot-plugin-mhcodes](https://github.com/padoru233/nonebot-plugin-mhcodes)，
由 [allenx555](https://github.com/allenx555) 维护 AstrBot 移植版。

- 集会码添加、查看、按内容或序号删除，以及手动清空。
- 按群和用户登记角色名称与常用武器。
- 记录集会码登记人和时间，固定显示北京时间。
- 可选每日自动清空，默认关闭；清空集会码时保留个人资料。

---

## 📸 预览

依次发送以下命令：

```text
/mh角色 猎人
/mh武器 太刀
/mh添加集会码 ABC123
/mh查看集会码
```

查看结果的文字示例（用户标识、集会码和日期均为示意，非实际 QQ 截图）：

```text
你的角色：猎人 ｜ 常用武器：太刀
📜当前集会码📜
1. ABC123
角色：猎人 ｜ 武器：太刀
登记人：示例用户ID
登记时间：2026-10-12 20:00:00 +0800
```

---

## 📦 安装

### 环境要求

- Python `>=3.12`，AstrBot `>=4.16,<5`。
- QQ OneBot v11 适配器（`aiocqhttp`）；其他平台未完成验证。
- 本插件没有额外运行依赖。

### 方式一：通过仓库地址安装（推荐）

在 AstrBot WebUI 插件管理中，使用以下仓库地址安装：

```text
https://github.com/allenx555/astrbot_plugin_mhcodes
```

安装或更新后，通过插件管理加载或重载，并查看插件日志。
本插件尚未完成插件市场提交；商店发布前仍需完成实际平台测试。

### 方式二：上传安装包

使用 `scripts/build_package.py` 生成安装 ZIP，再通过 AstrBot WebUI 插件管理上传安装。
运行依赖由插件管理器根据 `requirements.txt` 处理。

### 方式三：手动安装

在 AstrBot 的插件目录中克隆仓库：

```bash
cd AstrBot/data/plugins
git clone https://github.com/allenx555/astrbot_plugin_mhcodes.git
```

通过插件管理加载或重载插件。更新时同样优先重载插件，无需默认重启整个 AstrBot。

---

## 🛠️ 配置项

在 WebUI 插件卡片的配置入口修改，保存后重载插件。

| 配置项 | 类型 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `daily_reset_enabled` | 布尔值 | 每天自动清空所有群的集会码 | `false` |
| `reset_hour` | 整数 | 每日重置小时，范围 0–23；仅开启自动清空时生效 | `4` |

登记时间显示和每日清空都固定使用北京时间（UTC+8），不依赖容器时区，无需 `timezone` 设置。

### 每日自动清空

- 默认关闭，可随时使用 `/mh重置集会码` 手动清空当前群。
- 开启后，后台每分钟检查一次，到点后的空闲群将在一分钟内清空；执行命令前也会检查是否到期。
- 停机或禁用期间错过的重置，会在再次加载或操作时补做。
- 每日清空不主动发送群消息，时钟回退不会重复清空。
- 修改重置小时或重新开启自动清空可能改变有效周期，操作前请备份数据。

旧安装已经保存为 `true` 的配置不会因默认值变化自动关闭；更新时请在 WebUI 明确关闭。

---

## 📝 使用方法

### 群聊命令

| 命令 | 说明 |
| --- | --- |
| `/mh角色 猎人` | 登记或修改你在本群的角色名称 |
| `/mh武器 太刀` | 登记或修改你在本群的常用武器 |
| `/mh添加集会码 ABC123` | 添加集会码，记录登记人和时间 |
| `/mh查看集会码` | 显示你的资料，以及本群集会码、角色、武器、登记人和时间 |
| `/mh删除集会码 ABC123` | 按完整内容删除集会码 |
| `/mh删除序号 1` | 删除当前列表第 1 条；列表变化后请重新查看编号 |
| `/mh重置集会码` | 清空当前群集会码，保留角色和武器资料 |
| `/mh帮助` | 查看命令说明 |

### 输入格式与权限

- 统一使用 `/mh` 前缀，**命令与具体输入之间必须有空格**，例如 `/mh角色 猎人`。
- `/mh` 与中文子命令之间可以有空格，例如 `/mh 角色 猎人`。
- `/mh角色猎人`、`/mh武器太刀`、原中文裸命令、`i猎人` 和 `/w太刀` 不匹配。
- 仅响应群聊中的完整命令，无需 @；私聊和普通聊天中的提及不响应。
- 所有群员均可添加、删除和清空集会码。
- 不验证集会码的游戏格式，集会码内容可以包含空格。

示例角色名“猎人”取自[官方角色介绍](https://www.playstation.com/zh-hans-hk/games/monster-hunter-wilds/)
对玩家主角的称呼，并非确认创建角色界面的预填姓名；请登记你实际使用的名称。

### 资料与登记时间

角色和武器按平台实例、群和用户隔离，修改资料后列表展示最新资料。
手动重置与每日自动清空只删除集会码，保留个人资料。

重复添加同一码不会改变登记人和原登记时间。
登记时间仅用于人工判断，插件没有游戏服务查询接口，不能自动确认房间是否失效。

---

## 💾 数据与迁移

### 数据保存位置

持久化文件位于 AstrBot 数据目录下：

```text
data/plugin_data/astrbot_plugin_mhcodes/mh_codes.json
```

文件包含角色、武器、用户标识、集会码及登记时间；分享日志、备份或 Issue 前请先脱敏。
插件没有网络请求，不向外部服务上传这些数据。

群数据按平台实例 ID 与群 ID 共同隔离。读写事务使用异步锁并在线程中执行，
采用临时文件原子替换。读取损坏数据时明确报错并保留原文件，不自动清空或覆盖。
仅支持单个 AstrBot 进程管理同一数据文件。

### 从本插件旧版升级

1.1.x 使用数据格式 v2。读取本插件 1.0.0 的合法 v1 数据时，先保存
`mh_codes.json.v1.<唯一标识>.bak`，再原子升级。
旧记录的登记人和时间显示为未知，不编造日期。

回退到 1.0.0 前需停用插件并恢复 v1 备份；升级后新增的登记信息无法由旧版读取。

### 从 NoneBot 版本迁移

旧 NoneBot 的 `mh_codes.json` 不能直接覆盖新文件：旧格式只有群号，缺少平台实例和重置日期。
如需导入，应先备份并停用插件，显式指定平台实例并转换格式。
本移植未搬运任何生产数据。

如需停用或回滚，请通过插件管理操作，并保留配置与持久化数据。
插件不会自动修改其他插件或 AstrBot 主配置。

---

## ⚠️ 常见问题

### 1. `/help` 为什么没有显示这些命令？

请使用 `/mh帮助`。插件使用群聊过滤器和正则监听，各入口不会作为标准指令
出现在 WebUI 的指令管理中。

### 2. 发送命令没有响应？

确认在群聊中发送完整命令，且参数前有空格，例如 `/mh武器 太刀`。
检查插件是否启用、当前会话服务是否开启，以及配置文件是否选择了本插件。
通过插件管理重载后查看加载日志，再在真实 QQ 群测试。

### 3. 为什么每天清空，或者重新启用后集会码消失了？

检查 `daily_reset_enabled` 是否开启。开启时会补做错过的每日重置，
重新开启也可能清空旧码。无需自动清空时关闭此项，使用手动重置。

### 4. 登记时间能判断集会码是否有效吗？

只能辅助人工判断。插件不会连接游戏服务验证房间状态；失效后请按内容、序号删除，
或手动清空当前群。

---

## 🤝 开发与贡献

欢迎提交 [Issue](https://github.com/allenx555/astrbot_plugin_mhcodes/issues)
和 Pull Request。参与开发前请阅读[贡献指南](CONTRIBUTING.md)。
开发依据、API 约束及历史验证记录见 [DEVELOPMENT.md](DEVELOPMENT.md)。

### 自动检查

push 到 `main`、PR 和手动触发会运行：

- 完整插件单元测试、Ruff 检查与格式检查，以及安装包构建。
- AstrBot 4.16.0 和当前可安装的最新兼容 4.x 版本的真实 API 冒烟检查。

仓库已配置 Copilot 自动审查：针对发往默认分支的非草稿 PR 请求审查，
追加提交后重新审查；实际运行需要 PR 作者具备相应权限及可用额度。

### 验证范围

目前 47 项测试已通过，真实 API 冒烟检查已在 AstrBot 4.16.0 和 4.28.2 上通过。
入口单元测试使用 API 替身；真实 API 检查没有启动完整服务或连接 QQ。
尚未验证实际平台发送。

上线后请分别确认插件加载、真实群聊命令收发、跨群隔离，以及重载后的后台任务清理。
容器启动、HTTP 200 或测试通过不能替代实际 QQ 功能验证。

---

## 📄 开源协议

本项目基于 [MIT](LICENSE) 协议开源，保留原项目版权声明。
原始源码基线为 `fe8c0efb57b8f7a30f912e1d049d221b6745611f`。
官方模板仅用于确认目录与 API 结构，未复制其 AGPL 模板实现。

---

## 🙏 致谢

- [padoru233/nonebot-plugin-mhcodes](https://github.com/padoru233/nonebot-plugin-mhcodes) — 原始插件。
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — 插件运行框架。
- [iona-s/astrbot_plugin_imgexploration](https://github.com/iona-s/astrbot_plugin_imgexploration) — README 结构参考。
