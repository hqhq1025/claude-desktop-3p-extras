# viz 小组件指南

## basics
基本规则（每次都适用）

先想清楚这张图要回答什么问题，再动手。复杂主题的解释写在回复正文里，小组件只放图本身。

- `widget_code` 以 `<svg` 开头按 SVG 渲染，否则按 HTML 片段渲染。不要写 `<html>`、`<head>`、`<body>`。
- 代码顺序：先写一小段 `<style>`，再写内容，`<script>` 放最后。用 `<script src>` 引库时，这一行要写在用到它的内联脚本前面。脚本在整段代码到齐后才执行。不要写注释，它们只占篇幅。
- 小组件里不放标题和说明段落。标题、结论、解读写在回复正文里，图里只留标签、图例和必要的数值。
- 复杂度预算：一张图 4 到 6 个主要节点；盒子里的副标题不超过 8 个汉字或 5 个英文词；最多两种强调色。超出预算就拆：先给一张只有盒子的总览，再按子流程各画一张，图和图之间用一句正文衔接。
- 背景透明，跟随对话的深浅色主题。颜色只用 CSS 变量或预置类，不要写死白底、黑字或任何文字颜色的十六进制值，否则深色主题下看不清。
  - 文字：`--viz-fg`（正文）、`--viz-muted`（次要）。别名 `--text-primary`、`--text-secondary` 也可以用。
  - 底色和边框：`--viz-surface`（卡片）、`--viz-bg`、`--viz-border`。别名 `--surface-1`、`--border`。
  - 强调：`--viz-info`（蓝，选中态和链接）、`--viz-accent`（Claude 品牌色，只用于"交给 Claude"的按钮）、`--viz-danger`。
- 排版：只用两种字重，400 和 500，不用 600 和 700。HTML 正文 14px，小标题 16px，次要文字 12px，最小 11px。字体继承页面，不要另设。不用 emoji，需要图标时画简单的 SVG 线条图标。
- 外观扁平：边框 1px（`--viz-border`），圆角 8px，卡片 12px。不用渐变、阴影、模糊和发光。
- 尺寸：对话里的容器宽约 760px；用户开着侧边面板时约 515px，所以宽度用百分比或 `max-width`，不要写死总宽。高度由内容决定，小组件会自动长高。
- 布局反模式：不用 `position: fixed` 和 `100vh`，它们在自动长高的框架里会塌掉或无限增高；要演示弹窗，就画一个固定高度的假视口。不做嵌套滚动，内容多就拆分或折叠，只有 `viz.table` 可以在内部滚动。grid 列用 `minmax(0, 1fr)` 防止长内容撑破，宽表用 `table-layout: fixed`。
- 初始状态要能直接看到内容，不要把主要内容藏在 `display: none` 后面等脚本显示。
- 无障碍：HTML 开头放一个 `<p class="sr-only">一句话说明这张图</p>`；SVG 根节点加 `role="img"`，第一个子元素写 `<title>`。不要只靠颜色区分系列，另加标签、线型或图例。
- 数字一律取整到合适的位数再显示，例如 `12.4%`、`$5.2M`、`-$5M`，不要显示 `12.3456789`。
- 代码控制在 100 KB 以内。数据多时用 `data` 或 `data_file` 参数传，不要内联。
- 沙箱里不能用 `alert`、`confirm`、`prompt`，`localStorage` 也可能不可用。
- 网络：脚本、样式、字体可以从 cdn.jsdelivr.net、unpkg.com、cdnjs.cloudflare.com、esm.sh 加载，`fetch` 也只能访问这几个域名，例如取地图数据。其他请求都会被拦截。
- 鼠标悬停时右上角有工具栏：
  - 放大：150% 到 400%，在固定高度的视窗里拖动查看。
  - 侧边打开：把打开请求填进输入框，用户按回车后，Claude 在右侧浏览器面板打开一份独立副本。
  - 复制图片：把图复制成 PNG。
  - 保存：SVG 图存成 PNG 和 SVG；HTML 存成一个可以直接用浏览器打开的完整页面，用到 CDN 上的库时打开需要联网。文件写进 `~/Downloads`。
- 小组件在这一轮回复结束后才显示，回复进行中看不到是正常的。
- `show_widget` 的结果里带 `Side-pane URL`。数据点多的图表、长表格、复杂示意图，在同一轮用 Claude_Browser 的 `preview_start` 打开这个链接，面板已开着时用 `navigate`。表单、追问按钮和很小的图不要打开，侧边副本不能给 Claude 发消息。
- 回复里不要再贴一遍代码，用一两句话说明图里是什么、可以怎么操作。

## api
`window.viz` 提供的接口

| 接口 | 作用 |
|---|---|
| `viz.sendPrompt(text)` | 把一段文字交给对话，返回 Promise<是否送达>。这个宿主通常只把文字填进输入框，用户按回车才发出；Claude 还在回复时宿主会拒收，小组件会提示并自动重试，最多 3 分钟。按钮文字写成"填入追问 ↗"，不要写"发送"。 |
| `viz.setContext(value)` | 把小组件当前状态（选中项、筛选条件、计算结果）交给模型。用户下次发消息时模型才读得到（通过 `read_widget_context`）。传字符串或可 JSON 序列化的对象。 |
| `viz.data` / `viz.whenData()` | `data` 或 `data_file` 参数传进来的数据。`data_file` 的数据在工具返回后才到，所以写 `viz.whenData().then(data => ...)`。 |
| `viz.palette` | 8 个系列色，固定顺序：蓝、琥珀、青、紫、橙、绿、粉、灰。按当前主题给出深浅合适的值，画图前读一次。 |
| `viz.table(selector, rows, opts)` | 可点表头排序、可筛选的表格。`rows` 是对象数组；`opts.columns = [{key, label, format(v, row)}]`，`opts.maxHeight`，`opts.filter = false` 关掉筛选框，`opts.onChange(rows)` 拿到当前显示的行。 |
| `viz.form(selector, fields, opts)` | 提问表单，提交后答案填进输入框。见 forms 一节。 |
| `viz.loadScript(url)` | 加载一个 CDN 脚本，返回 Promise。 |
| `viz.download(name, data, mime)` | 保存文件，`data` 可以是字符串或 Blob，文件写进 `~/Downloads`，返回 `{ok, path}`。图表库自带的"导出 PNG"按钮也会自动走这里。 |
| `viz.openLink(url)` | 让宿主打开外部链接，宿主会先请用户确认。用 https、mailto、tel 或 sms 链接，宿主拒绝 http；`<a href>` 和 `window.open` 会自动走这里。 |
| `viz.fullscreen()` | 这个宿主只有内联模式，会返回 `{unsupported: true}`，不要依赖它。 |
| `viz.theme` | 当前主题，`"light"` 或 `"dark"`。 |

## charts
图表

先选形式，再配色。

| 要表达的 | 用什么 |
|---|---|
| 一个关键数字 | 数字卡：大号数值、一行标签、可选的环比 |
| 3 到 5 个头条数字 | 一排数字卡 |
| 占比、完成度 | 进度条（meter），不用饼图 |
| 随时间变化 | 折线图；类别少、要比大小时用柱状图 |
| 类别间比大小 | 横向柱状图，按数值排序 |
| 两个变量的关系 | 散点图 |
| 超过 7 个类别或要看精确值 | 表格（`viz.table` 或回复里的 Markdown 表） |

配色规则：

- 颜色跟着含义走。比较同一类东西用 `viz.palette` 的固定顺序；只突出一项时，用一个颜色加其余灰色；正负对比用蓝和橙两端。
- 同一个实体在所有图里用同一个颜色，筛选、排序后颜色不变。
- 系列超过 8 个时，把小的归成"其他"。不用彩虹色。
- 只用一根 y 轴。两个量纲不同的指标分成两张小图，上下排列。

图表外观：

- 关掉库自带的图例，改用 HTML 图例：小色块加名称，必要时加数值。
- 坐标轴文字、刻度、标签用 `--viz-muted`，不要用系列色。网格线用 `--viz-border`，只画横线；时间轴不画竖网格线。
- 柱宽不超过 24px，柱间留白不小于柱宽的一半。折线 2px。面积图填充用系列色的 10% 透明度。
- 图例、坐标轴标题和单位写清楚。数据点多时用悬停提示，不要把每个数都标在图上。

库和写法：

- 简单的柱状图、折线图手写 SVG：可控、加载快、能导出 PNG。需要坐标轴、悬停提示、缩放或大量数据点时用库：
  - Chart.js：`https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`
  - ECharts：`https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js`
  - D3：`https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js`
- 图表库的颜色不会自动跟随主题。从 CSS 变量读颜色再传给库：`getComputedStyle(document.documentElement).getPropertyValue('--viz-muted').trim()`。
- Chart.js：高度写在外层 div 上（`<div style="position:relative;height:320px"><canvas></canvas></div>`），设 `maintainAspectRatio: false`。横向柱图的高度取"条数 × 40 + 80"px。类别不超过 12 个时设 `ticks.autoSkip: false`，否则标签会被跳过。气泡图和散点图给坐标轴留出余量，避免点被裁掉。
- 地图不要手画坐标。用 D3 加 jsdelivr 上的 `world-atlas` 或 `us-atlas` 拓扑数据，可以 `fetch` 取到。

## diagrams
流程图、架构图、示意图

按用户的问法选图型：

| 用户问 | 画什么 |
|---|---|
| "X 是怎么工作的" | 示意图：用空间位置讲机制，例如数据从左流到右、层层包裹 |
| "有哪些步骤""流程是什么" | 流程图：从上到下或从左到右，一条主线 |
| "架构是什么""由哪些部分组成" | 结构图：分组框加连线 |
| 循环过程 | 不画成一个圈；做成 HTML 分步器，"上一步 / 下一步"逐步高亮 |
| 数据库表关系、类关系 | Mermaid 的 ERD 或类图 |

画布：

- SVG 根节点写 `viewBox="0 0 680 H"`，宽度固定 680，不要缩小 viewBox 来"放大"内容，那会把字也放大。内容窄就居中摆放。H 取最低元素的底边再加 24 到 40。所有坐标为正数，四周留 16px 安全边距。
- 一次调用只放一个根 `<svg>`。

先测宽，再画盒子。SVG 不会自动换行，盒子要按文字的实际宽度来定：

- 14px 字号下，每个汉字约 14px 宽，英文字母和数字平均约 8px，公式、符号多的文字再多留 30% 到 50%。
- 盒宽 = 最长一行文字的宽度 + 左右内边距各 12 到 16px。同一排盒子先把宽度和间距加起来，确认总宽不超过 648。
- 盒内文字用 `text-anchor="middle"` 和 `dominant-baseline="central"`，定位在盒子中心。要换行就用 `<tspan x=".." dy="1.3em">`，但更好的办法是把文字改短。

预置类（深浅主题自动切换，优先用它们，不要自己写颜色）：

| 类 | 作用 |
|---|---|
| `t` | 14px 正文文字 |
| `th` | 14px 字重 500，盒子标题 |
| `ts` | 12px 次要文字 |
| `box` | 中性盒子：卡片底色加边框 |
| `arr` | 连线：无填充、1.5px 次要色 |
| `leader` | 引线：1px 虚线 |
| `node` | 可点击节点：鼠标变手形，悬停加粗边框 |
| `c-blue` `c-teal` `c-green` `c-amber` `c-red` `c-purple` `c-coral` `c-pink` `c-gray` | 色带：浅底、同色边框、深色文字；深色主题下自动反过来 |

- 色带类加在包住"形状加文字"的 `<g>` 上，或直接加在 `rect`、`circle`、`ellipse`、`polygon` 上；不要加在 `path` 上。所有 `<text>` 都带 `t`、`th` 或 `ts` 之一。
- 颜色按含义分配：一张图 2 到 3 种颜色，普通节点用 `box` 或 `c-gray`；蓝表示信息或当前步骤，绿表示成功，琥珀表示警告，红表示错误。不要按顺序把每个节点涂成不同颜色。

连线：

- 页面预置了箭头 `#arrow`，颜色跟随线条：`<path class="arr" d="M.. .." marker-end="url(#arrow)"/>`。
- 用 `path` 当连线时，一定写 `fill="none"` 或带 `arr` 类，否则会被填成黑色块。
- 画每条线前检查它会不会穿过别的盒子。会穿过就改成 L 形折线（`M x1 y1 H xm V y2 H x2`）。线的两端停在盒子边缘，不要伸进盒子里。
- 尽量不给连线加文字标签；必须加时，放在线段旁边的空白处，不要压在线上。

其他：

- 示意图里的标签集中放在一侧，用 `leader` 引线连到对应部位；任何线条都不能压住文字。造型保持简单，几何形状就够了。
- 纯 SVG 模式下，内容超出 viewBox 时小组件会自动扩大 viewBox，但这时字会变小；HTML 片段里的 SVG 不做这项修正。所以还是按上面的规则算好尺寸。
- Mermaid 只用于 ERD 和类图：`await viz.loadScript('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js')`，`mermaid.initialize({startOnLoad: false, theme: viz.theme === 'dark' ? 'dark' : 'default'})`，`const {svg} = await mermaid.render('m1', text)`，再把 `svg` 放进容器。节点多的流程图不要交给 Mermaid，先拆图。
- 公式用 KaTeX：样式 `https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css`（用 `<link rel="stylesheet">`），脚本 `https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js`，然后 `katex.render(tex, el)`。
- 可点击的 SVG 图要写成 HTML 片段：外层 `<div>` 里放 `<svg>`，再用 `<script>` 给节点绑定点击事件。纯 SVG 模式不执行脚本。

## forms
提问表单（代替连续追问）

先从上下文推断。能从对话里推断出来的，就直接按推断做，并在回复里说明假设；只有真正需要用户决定的问题才出表单。

- 每题写成一句完整的问话，例如"这次优化最看重哪一点？"，不要写成字段名"目标"。
- 一张表单 2 到 5 题。选项给 3 到 5 个，覆盖常见情况；需要时在 options 末尾加"其他"，并配一个 `text` 题让用户补充。
- 题目多时不要全用胶囊按钮，按问题选控件：数量和程度用 `range`，日期用 `date`，开放问题用 `textarea`。

```js
viz.form('#q', [
  { id: 'goal', label: '这次优化最看重哪一点？', type: 'choice', options: ['速度', '成本', '质量', '其他'] },
  { id: 'scope', label: '要改动哪些模块？', type: 'multi', options: ['前端', '后端', '数据'] },
  { id: 'date', label: '希望什么时候上线？', type: 'date' },
  { id: 'note', label: '还有什么要补充的吗？', type: 'textarea', placeholder: '可选' },
], { submitLabel: '填入回答 ↗', intro: '我的选择：' });
```

`type` 可选 `choice`（单选）、`multi`（多选）、`text`、`textarea`、`number`、`date`、`range`（可带 `min`、`max`、`step`）。提交后答案以列表形式填进输入框，用户按回车后你在下一轮读到。不支持上传文件；需要文件时请用户给出本机路径，再用 `data_file` 读取。

## data
数据怎么传

- 数据量小（几十行以内）：直接写在代码里。
- 数据量中等，或想把数据和代码分开：用 `data` 参数传 JSON，代码里用 `viz.data`。
- 数据在本地文件里（CSV、TSV、JSON、JSONL，5 MB 以内）：用 `data_file` 参数传绝对路径。服务端读取文件，CSV 会解析成对象数组并把数字转成数值，再交给小组件。模型只收到行数、列名和前几行样例，整份数据不进上下文。代码里写 `viz.whenData().then(rows => { ... })`。
- 小表（20 行以内、不需要排序）在回复里写 Markdown 表；大表或要排序、筛选时用 `viz.table`。

## patterns
推荐的交互方式

- 只有需要 Claude 思考的动作才调用 `viz.sendPrompt`，例如"深入分析这一项"。筛选、排序、切换系列、重新计算都在小组件里用 JS 完成，不往返对话。
- 调用 `sendPrompt` 的按钮在文字后加 ↗，让用户知道点了会交给 Claude。只给关键节点加，用户每点一次都要回到输入框按回车。
- 参数探索：用滑块实时重算并重画，再用 `viz.setContext` 把用户最终选的参数交给模型。
- 讲解机制：分步器，"上一步 / 下一步"按钮，每一步高亮一部分并显示一句说明。
- 方案对比：每个方案一张卡片，并排放；推荐的那张用 2px 的 `--viz-info` 边框，并在卡片顶部标"推荐"。
- 数字卡：浅色卡片（`--viz-surface`），上面一行 12px 次要色标签，下面一行 24px 数值，字重 500。
- 界面草图（mockup）放在一个 `--viz-surface` 底色、12px 圆角的容器里，和对话内容区分开。
- 动画只改 `transform` 和 `opacity`，时长 150 到 300ms，并用 `@media (prefers-reduced-motion: reduce)` 关掉。
- 复杂主题可以分几个小组件，每个回答一个问题，中间用一两句正文衔接；不要把所有内容塞进一张大图。
