# Claude Desktop 3p 模式：在对话里显示可交互的图（viz）

在 1p 模式下，Claude 能调用内置工具 `show_widget`，把图表、示意图和表格直接画在对话里。在第三方推理（3p）模式下，这个功能由一个 GrowthBook 开关控制。3p 内置的开关表里没有这个开关，所以它一直是关的，改配置也打不开。

viz 是一个本地 MCP 服务，提供同名工具 `show_widget`。它通过 MCP Apps 协议，在 Code 会话里内联显示可交互的图。服务只用 Python 标准库，不用安装依赖。

测试环境：macOS，Claude Desktop 4.4212.0（3p 模式），Code 会话。Chat 和 Cowork 没有测试。Desktop 的行为可能随版本变化。

## 1. 原理

MCP 服务注册在不同位置时，Desktop 对它的 MCP App 支持不同：

| 注册位置 | 3p 下能否内联显示 | 原因 |
|---|---|---|
| Claude Code 的配置（`~/.claude.json`、`.mcp.json`） | 不能 | Desktop 只在开关 `513873720` 打开时，才让 Claude Code 当 MCP App 宿主。3p 下这个开关是关的 |
| Desktop 的 `claude_desktop_config.json` 里的 `mcpServers` | 能 | Desktop 自己启动这个服务、渲染它的页面。界面端对应的开关在 3p 下默认打开 |

所以 viz 要注册在 Desktop 的配置里。

```text
Claude ── show_widget(title, code, data) ──> viz 服务 ──> 工具结果 + 页面资源 ui://viz/widget-<哈希>.html
Desktop 在沙箱 iframe 里加载 widget.html，把 code 和 data 交给页面渲染
```
图：一次 `show_widget` 调用的数据流。

## 2. 目录内容

| 文件 | 用途 |
|---|---|
| `viz_widget_server.py` | MCP 服务，经 stdio 收发 JSON-RPC |
| `widget.html` | 小组件页面：渲染 SVG 或 HTML 片段，提供 `viz` 接口和工具栏 |
| `guide.md` | 给 Claude 看的设计与接口指南，工具 `read_me` 返回它的内容 |
| `register.py` | 把前三个文件复制到安装目录；等 Desktop 退出后，把 viz 写进 Desktop 配置，再重新打开 Desktop |

## 3. 安装

1. 仓库可以放在任何位置。`register.py` 把 `viz_widget_server.py`、`widget.html` 和 `guide.md` 复制到安装目录（默认 `~/.local/share/viz-widget`，用 `--dir` 指定其他目录），Desktop 配置里记录的是安装目录里的路径。

   安装目录不能在 `~/Documents`、`~/Desktop`、`~/Downloads` 或 iCloud 云盘下。这些目录受 macOS 隐私保护（TCC）。Desktop 给 Code 会话启动服务的进程不一定有访问权限，服务会随机报 `Operation not permitted` 并退出，界面显示 viz 不可用。用符号链接指向这些目录也一样会失败。
2. 查看将要写入的配置：

   ```bash
   python3 viz/register.py --print
   ```

3. 运行注册脚本，然后用 Cmd+Q 完全退出 Desktop：

   ```bash
   python3 viz/register.py
   ```

   脚本在后台等 Desktop 退出，备份配置后写入 `mcpServers.viz`，再自动打开 Desktop。进度记在 `/tmp/viz-register.log`。

退出后不要自己马上重新打开 Desktop。原因是 Desktop 只在启动时读一次 `claude_desktop_config.json`，运行时会把内存里的整份配置写回文件。如果在脚本写入之前打开了 Desktop，新实例会用旧配置覆盖脚本的修改。

也可以手动注册：完全退出 Desktop，在 `~/Library/Application Support/Claude-3p/claude_desktop_config.json` 的 `mcpServers` 里加上 `--print` 输出的条目，再打开 Desktop。

## 4. 使用

在新的 Code 会话里让 Claude 画图，例如“把这份 CSV 画成柱状图”。Claude 先调用 `read_me` 读设计指南，再调用 `show_widget`。

- `widget_code` 以 `<svg` 开头时按 SVG 渲染，否则按 HTML 片段渲染，`<script>` 会执行。0.8 之前的字段名 `code` 仍然接受。
- `data` 传 JSON。`data_file` 传本机 CSV、TSV、JSON 或 JSONL 文件的绝对路径（不超过 5 MB），服务读取后直接交给页面，模型只收到行数、列名和几行样例。
- 页面里有全局对象 `viz`，提供 `sendPrompt`、`setContext`、`table`、`form`、`loadScript`、`download` 等接口，详见 `guide.md`。
- 页面颜色跟随对话的深浅色主题。页面预置了一套 SVG 类：文字 `t`、`ts`、`th`，中性盒子 `box`，连线 `arr`、`leader`，9 条深浅自适应的色带 `c-blue`、`c-teal` 等，以及共用的箭头 `#arrow`。另有常见 token 名的别名，例如 `--text-primary`、`--surface-1`、`--border`。
- 脚本、样式和字体可以从 cdn.jsdelivr.net、unpkg.com、cdnjs.cloudflare.com 和 esm.sh 加载；`fetch` 也可以访问这四个域名，例如读取地图数据。

小组件在这一轮回复结束后才显示。鼠标移到小组件上，右上角会出现工具栏：

| 按钮 | 作用 |
|---|---|
| 放大 | 在小组件内放大到 150% 到 400%，可以拖动，或按住 Ctrl 或 ⌘ 用滚轮缩放 |
| 侧边打开 | 把打开请求填进输入框，按回车后 Claude 在右侧浏览器面板打开一份副本 |
| 复制图片 | 把图复制成 PNG。宿主不允许页面写剪贴板时，由服务写进 macOS 剪贴板 |
| 保存 | SVG 图保存为 PNG 和 SVG，导出的 SVG 自带样式和箭头定义；HTML 保存为可以离线打开的完整页面，主题、`viz` 接口和数据都保留。文件写进 `~/Downloads` |

页面还会接管几类操作：`window.open` 和外链交给宿主打开，图表库自带的“导出图片”链接转成保存，表单的原生提交被拦下，避免框架跳到空白页。SVG 的内容超出 `viewBox` 时，页面会自动扩大 `viewBox`。

侧边副本：每次调用 `show_widget`，服务都会在 `127.0.0.1` 的随机端口上存一份同样的页面，并在工具结果里附上链接。图的细节较多时，Claude 会在同一轮用内置浏览器打开这个链接。这时右侧面板显示大图，对话里还会出现一张带缩略图的浏览器卡片。这需要在 3p 配置里打开内置浏览器（`"builtinBrowserEnabled": true`）。侧边副本不能给 Claude 发消息，所以表单和追问按钮只在对话里的小组件上有效。

## 5. 宿主限制

以下是在 Desktop 4.4212.0 上实测的结果。

| 限制 | viz 的处理 |
|---|---|
| 没有下载对话框（不支持 `ui/download-file`） | “保存”和 `viz.download` 由服务写进 `~/Downloads` |
| 只有内联显示，没有全屏 | 提供“放大”和“侧边打开” |
| 拒绝打开 `http://127.0.0.1` 的链接（`ui/open-link` 返回 `isError`） | “侧边打开”经过对话，由 Claude 打开右侧面板 |
| Claude 回复期间，宿主拒收小组件发来的消息（`ui/message`） | 小组件提示后自动重试，最多 3 分钟 |
| `ui/message` 通常只把文字填进输入框，并且每次都追加 | 提示按回车；同一个请求不会重复填入 |
| 每个小组件只保留最后一次 `ui/update-model-context` | `viz.setContext` 和错误信息合并成一次发送。用户下次发消息时，Claude 才能读到 |
| 从历史记录重新显示小组件时，不再提供工具结果里的数据 | 页面通过服务重新读取 `data_file` |

下面几项来自对 Desktop 4.4212.0 渲染端代码的阅读，没有逐项实测。Code 页签按 `server.isBuiltIn` 区分内置的 visualize 小组件和第三方 MCP App，改工具名或服务名都不能让第三方服务变成内置服务。

| 内置 visualize 有、第三方没有 | viz 的处理 |
|---|---|
| 边生成边显示（`tool-input-partial`）。第三方小组件要等工具调用结束才挂载 | 无法补；guide 要求脚本放最后，内容先写 |
| 工具卡片上的 `loading_messages` | 不提供这个参数 |
| 宿主代为复制、下载（`ui/download-file`）、直接发送消息 | 复制和保存由服务完成；消息只能填进输入框 |
| `ui/open-link` 免确认 | 第三方的链接只接受 https、mailto、tel、sms，打开前宿主会请用户确认 |

## 6. 更新与诊断

- Desktop 会缓存小组件页面，而且跨会话保留。改了 `widget.html` 后，要完全退出再打开 Desktop 才会生效；换资源地址、重启服务、新开会话都不行。服务把页面的哈希写进资源地址，保证重启后读到新页面。
- 改了 `viz_widget_server.py` 后，结束服务进程即可。Desktop 会在下一次调用工具时重新启动服务。

  ```bash
  ps -axo pid,comm,command | grep '[v]iz_widget_server'
  ```

  对其中的 Python 进程发送 SIGTERM。当前会话缓存的工具说明要等新会话才更新。
- 改完仓库里的文件后，运行 `python3 viz/register.py --sync`（装在其他目录时加同样的 `--dir`），把文件复制到安装目录。只复制文件，不改 Desktop 配置。
- `guide.md` 在每次调用 `read_me` 时重新读取，同步后立即生效。
- 单个请求出错（例如读不到文件）时，服务返回 JSON-RPC 错误并记进日志（事件 `request-error`），进程继续运行。
- 服务和页面把事件写进 `~/Library/Logs/viz-widget/server.log`，包括工具调用、页面版本、宿主能力、渲染结果、脚本错误和按钮操作。工具返回“Rendered … inline”只说明服务收到了调用。要确认页面是否真的显示出来，看日志里有没有 `widget:rendered`。

## 7. SSH 远程会话

在 SSH 远程会话里，Desktop 把本机的 MCP 服务交给远程主机，由远程主机按同一条命令启动。实测发现，远程会话里的 MCP App 小组件不会显示，脚本也不执行。所以服务在非 macOS 主机上不提供任何工具，以免 Claude 以为图已经显示。远程会话里可以改用 Markdown 图片：把 SVG 或 PNG 写在远程会话的工作目录里，在回复中用绝对路径引用。

安装目录在本机的主目录下时，`register.py` 写入的命令是相对 `$HOME` 的路径（默认 `$HOME/.local/share/viz-widget/viz_widget_server.py`）。远程主机的同一位置没有这些文件时，远程会话会提示 viz 启动失败，但不影响其他功能。想去掉这个提示，就把安装目录里的 `viz_widget_server.py`、`widget.html` 和 `guide.md` 复制到远程主机的同一位置。

## 8. 安全说明

- 小组件页面运行在 Desktop 的沙箱 iframe 里。网络请求只允许访问上面三个 CDN。
- 侧边副本的服务只监听 `127.0.0.1`，每个页面的链接里有一段随机令牌。每个服务进程最多保留 100 个页面，进程退出后链接失效。
- “保存”只写 `~/Downloads`，不覆盖已有文件，单个文件不超过 20 MB。
- 页面用到的辅助工具（`widget_report`、`widget_save`、`widget_data`、`widget_open`）只对页面可见，Claude 看不到也调用不了。
