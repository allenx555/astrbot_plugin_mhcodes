# Review guidance

- Respond in Chinese. Focus on actionable bugs, regressions and missing meaningful checks.
- This is an AstrBot plugin, with minimum supported AstrBot version 4.16.0.
- Preserve the MIT license and attribution to the original NoneBot plugin.
- Commands use the mh prefix and Chinese subcommands. Arguments require whitespace.
- Profiles are isolated by platform instance, group and user. Codes retain owner and original registration time.
- Manual code reset preserves profiles. Daily reset defaults to disabled. Time display is fixed UTC+8; do not introduce a timezone configuration.
- Persistent data belongs outside the plugin source directory. Check atomic writes, transaction locking, cancellation and hot reload cleanup.
- Prefer plugin-manager reload over restarting the whole AstrBot service.
- Unit tests use framework substitutes. The API smoke script uses real AstrBot APIs but does not connect QQ. Do not describe either as actual QQ delivery verification.
- Never include tokens, user data or real lobby codes in logs, examples or review comments.
