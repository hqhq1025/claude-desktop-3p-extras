# Claude Desktop 3p 模式扩展

Claude Desktop 的第三方推理（3p）模式下，有些功能用不了，或者需要额外配置才能用。本仓库收集了几种做法，都不用修改 Desktop 安装包。

| 目录 | 解决的问题 |
|---|---|
| [`ssh-gateway/`](ssh-gateway/README.md) | 模型网关跑在本机时，打开 SSH 远程会话，并让远程主机使用它自己的网关 |
| [`viz/`](viz/README.md) | 在 Code 会话里内联显示可交互的图表、示意图和表格，代替 3p 下关闭的内置 `show_widget` |

测试环境：macOS，Claude Desktop 4.4212.0。Desktop 的行为可能随版本变化。

## License

MIT
