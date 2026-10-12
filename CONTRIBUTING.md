# 参与开发

请保持改动集中。行为或配置变化需要同步更新 README 和相关测试，保留移植来源及 MIT 许可证。
提交者应理解并人工审查全部改动，包括 AI 辅助生成的内容。

## 本地检查

在插件目录中执行：

```powershell
uv run --no-project --with pytest python -m pytest -q
uv run --no-project --with ruff ruff check .
uv run --no-project --with ruff ruff format --check .
uv run --no-project --python 3.12 --with "astrbot==4.16.0" python scripts/smoke_astrbot.py
python scripts/build_package.py
```

开发中运行改动相关测试，提交推送前运行完整插件测试。API 冒烟检查只验证真实框架 API，
没有连接 QQ；实际平台验证请另外记录插件加载日志、具体命令及收发结果。
部署后优先通过 AstrBot 插件管理页面/API 重载插件。

## 自动检查与模板

- `.github/workflows/ci.yml`：push 到 main、PR 和手动触发时运行完整单元测试、Ruff、打包检查，
  以及最低版本 4.16.0 和当前可安装的最新兼容 AstrBot 4.x API 冒烟检查。
- `.github/PULL_REQUEST_TEMPLATE.md`：PR 改动、验证结果与提交检查清单。
- `.github/ISSUE_TEMPLATE/`：Bug 和功能建议表单。
- `.github/CODEOWNERS`：请求 allenx555 审核。
- `.github/copilot-instructions.md`：Copilot 审查的项目约定。

Copilot 自动审查由 GitHub 仓库 Rulesets 配置，不是仓库中的 YAML 工作流。
PR 作者需要具备 Copilot code review 使用权限及可用额度；审查建议不替代 CI 或人工检查。
插件商店展示使用根目录 `metadata.yaml`，提交市场仍需通过 AstrBot Cloud 完成。
