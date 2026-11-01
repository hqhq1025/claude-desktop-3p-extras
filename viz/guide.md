# viz 小组件指南

## basics
基本规则（每次都适用）

- `code` 以 `<svg` 开头按 SVG 渲染，否则按 HTML 片段渲染。不要写 `<html>`、`<head>`、`<body>`，`<style>` 和 `<script>` 可以直接写在片段里。
- 背景透明，跟随对话的深浅色主题。颜色只用这些 CSS 变量：`--viz-fg`（正文）、`--viz-muted`（次要文字）、`--viz-border`、`--viz-surface`（卡片底色）、`--viz-bg`、`--viz-accent`（强调色）、`--viz-danger`。不要写死白色背景或黑色文字，否则深色主题下看不清。
- 数据系列配色用 `viz.palette`（8 种颜色，深浅主题下都可读）。同一张图里一种颜色只代表一种含义。
- 字体继承页面字体，不要另设。正文 13–14px，标题 15–16px。
- 宽度自适应（不要写死总宽度），高度由内容决定。对话里内联显示时，高度控制在约 600px 以内。容器宽约 760px。内容多时给容器加滚动或做成分页、折叠。这个宿主不支持全屏。
- 代码控制在 100 KB 以内。数据较多时用 `data` 或 `data_file` 参数传，不要内联进代码。
- 沙箱里不能用 `alert`、`confirm`、`prompt`，`localStorage` 也可能不可用。
- 网络：脚本、样式、字体只能从 cdn.jsdelivr.net、unpkg.com、cdnjs.cloudflare.com 加载，其他请求（fetch、XHR）都会被拦截。
- 鼠标悬停时右上角有工具栏："放大"（150%–400%，固定高度视窗里拖动或 Ctrl/⌘+滚轮缩放，适合看细节）、"侧边打开"（把打开请求填进输入框，用户按回车后 Claude 在右侧浏览器面板打开一份独立副本，面板更宽更高，图表和表格照常可用，但不能发消息给 Claude）、"保存"（SVG 图保存成 PNG 和 SVG，HTML 保存成单个 HTML 文件，写进运行 viz 服务那台机器的 `~/Downloads`）。细节多的图不必挤在一屏里，用户可以自己放大或开新窗口。
- 小组件在这一轮回复结束后才显示出来，回复进行中看不到是正常的。
- `show_widget` 的结果里带 `Side-pane URL`。数据点多的图表、长表格、复杂示意图，在同一轮用 Claude_Browser 的 `preview_start` 打开这个链接；面板已开着时用 `navigate`。这样右侧面板显示大图，对话里也会多一张带缩略图的浏览器卡片。表单、追问按钮和很小的图不要打开，侧边副本不能发消息。
- 回复里不要再贴一遍代码，用一两句话说明图里是什么、可以怎么操作。

## api
`window.viz` 提供的接口

| 接口 | 作用 |
|---|---|
| `viz.sendPrompt(text)` | 把一段文字交给对话，返回 Promise<是否送达>。这个宿主通常只把文字填进输入框，用户要按回车才发出（小组件会提示）；Claude 还在回复时宿主会拒收，小组件会提示并自动重试，最多 3 分钟。按钮文字写成"填入追问：…"比"发送"更准确。适合"深入看看这一项"这类追问按钮。 |
| `viz.setContext(value)` | 把小组件当前状态（选中项、筛选条件、计算结果）交给模型。用户下次发消息时模型才能读到（通过 `read_widget_context`）。传字符串或可 JSON 序列化的对象。 |
| `viz.data` / `viz.whenData()` | 通过 `data` 或 `data_file` 参数传进来的数据。`data_file` 的数据在工具返回后才到，所以用 `viz.whenData().then(data => ...)`。 |
| `viz.table(selector, rows, opts)` | 可点表头排序、可筛选的表格。`rows` 是对象数组；`opts.columns = [{key, label, format(v, row)}]`，`opts.maxHeight`，`opts.filter = false` 关掉筛选框，`opts.onChange(rows)` 拿到当前显示的行。 |
| `viz.form(selector, fields, opts)` | 提问表单，提交后把答案作为用户消息发出。见 forms 一节。 |
| `viz.loadScript(url)` | 加载一个 CDN 脚本，返回 Promise。 |
| `viz.download(name, data, mime)` | 保存文件，`data` 可以是字符串或 Blob。这个宿主没有下载对话框，文件由 viz 服务写进 `~/Downloads`，返回 `{ok, path}`。 |
| `viz.fullscreen()` | 宿主支持时切换全屏；这个宿主只有内联模式，会返回 `{unsupported: true}`，不要依赖它。 |
| `viz.openLink(url)` | 用宿主打开外部链接。普通 `<a href="https://...">` 会自动走这个。 |
| `viz.theme` | 当前主题 `"light"` 或 `"dark"`。 |

## charts
图表

- 简单的柱状、折线、散点、饼图直接手写 SVG：可控、加载快，下载按钮还能导出 PNG。
- 需要坐标轴、悬停提示、缩放、大量数据点时用图表库。先 `await viz.loadScript(url)` 再画：
  - Chart.js：`https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`
  - ECharts：`https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js`
  - D3：`https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js`
- 图表库的颜色不会自动跟随主题。从 CSS 变量读颜色再传给库：`const fg = getComputedStyle(document.documentElement).getPropertyValue('--viz-fg').trim()`。网格线用 `--viz-border`，文字用 `--viz-muted`。
- Chart.js 的容器要给固定高度（例如 `<div style="height:320px"><canvas></canvas></div>`），并设 `maintainAspectRatio: false`。
- 图例、坐标轴标题、单位写清楚。数值多时加悬停提示，不要把每个数字都标在图上。

## diagrams
流程图、架构图、示意图

- 结构简单时手写 SVG：设 `viewBox`，宽度用 100%，文字用 `fill="var(--viz-fg)"`，连线和边框用 `var(--viz-border)` 或 `var(--viz-muted)`，重点用 `var(--viz-accent)`。
- 节点多、自动布局省事时用 Mermaid：`await viz.loadScript('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js')`，然后 `mermaid.initialize({startOnLoad:false, theme: viz.theme === 'dark' ? 'dark' : 'default'})`，`const {svg} = await mermaid.render('m1', text)`，把 `svg` 放进容器。
- 公式用 KaTeX：样式 `https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css`（用 `<link rel="stylesheet">`），脚本 `https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js`，然后 `katex.render(tex, el)`。
- 可交互的示意图（点节点看说明、切换步骤）比静态图更好讲清机制：把每个节点的说明放在 `data-*` 属性里，点击时显示在图下方的说明栏。

## forms
提问表单（代替连续追问）

需要用户一次回答几个问题时，用表单把问题放在一张卡片里：

```js
viz.form('#q', [
  { id: 'goal', label: '主要目标', type: 'choice', options: ['速度', '成本', '质量'] },
  { id: 'scope', label: '涉及的模块', type: 'multi', options: ['前端', '后端', '数据'] },
  { id: 'date', label: '截止日期', type: 'date' },
  { id: 'note', label: '补充说明', type: 'textarea', placeholder: '可选' },
], { submitLabel: '提交', intro: '我的选择：' });
```

`type` 可选 `choice`（单选胶囊）、`multi`（多选胶囊）、`text`、`textarea`、`number`、`date`、`range`（可带 `min`、`max`、`step`）。提交后答案以列表形式填进输入框（宿主有时直接发出），用户按回车后你在下一轮读到。

## data
数据怎么传

- 数据量小（几十行以内）：直接写在代码里。
- 数据量中等，或想把数据和代码分开：用 `data` 参数传 JSON，代码里用 `viz.data`。
- 数据在本地文件里（CSV、TSV、JSON、JSONL，5 MB 以内）：用 `data_file` 参数传绝对路径。服务端读取文件，CSV 会解析成对象数组并把数字转成数值，然后交给小组件。模型只会收到行数、列名和前几行样例，不会把整份数据放进上下文。代码里写 `viz.whenData().then(rows => { ... })`。
- 表格数据先考虑 `viz.table`，它自带排序和筛选。

## patterns
推荐的交互方式

- 下钻：图上的每一项配一个按钮或点击事件，调用 `viz.sendPrompt('详细分析一下 X')`。
- 对比：用胶囊按钮或下拉框切换数据系列，在小组件内重画，不需要往返对话。
- 参数探索：用滑块（`<input type="range">`）实时重算并重画，再用 `viz.setContext` 把用户最终选的参数交给模型。
- 讲解机制：分步动画或"上一步/下一步"按钮，每一步高亮一部分并显示说明。
- 一次回复里只放一个小组件，除非用户要对比多个。
