# Claude Desktop 3p 模式：用本机模型网关开 SSH 远程会话

在 Claude Desktop 的第三方推理（3p）模式下，如果模型网关跑在本机（例如 `http://127.0.0.1:3425`），Desktop 会拒绝开 SSH 远程会话。本仓库说明怎样配置，才能让本机和远程主机各自使用自己机器上的网关，同时打开 SSH 远程会话。

文中的“网关”指 Desktop 配置项 `inferenceGatewayBaseUrl` 指向的模型服务，例如 [magpie](https://github.com/yetone/magpie)、LiteLLM 或其他兼容 Anthropic Messages API 的本地代理。示例中的端口按 magpie 写，换成其他网关时改端口即可。

测试环境：macOS，Claude Desktop 4.4212.0（内置 Claude Code 2.1.286）；远程主机是 Linux 容器，远程会话使用的 Claude Code 为 2.1.309。Desktop 的行为可能随版本变化。

## 1. 原理

Desktop 对网关地址做两次检查：

| 检查 | 规则 | `http://127.0.0.1:3425` | `http://local-gw:3425` | `https://local-gw:3443` |
|---|---|---|---|---|
| 配置校验 | 应为 https；http 只允许字面主机名 `127.0.0.1`、`localhost`、`[::1]` | 通过 | 不通过，整条网关配置失效 | 通过 |
| 远程会话 | 主机名字面是回环地址时拒绝，不做 DNS 解析 | 拒绝 | 通过 | 通过 |

所以网关地址应写成 `https://<别名>:<端口>`，别名不能是回环地址的字面写法。本仓库用别名 `local-gw`：

1. 本机和远程主机都在 `/etc/hosts` 中把 `local-gw` 指向 `127.0.0.1`。
2. 两台机器各自在 `127.0.0.1:3443` 提供 HTTPS，再把请求转给本机的网关。
3. 两台机器都信任同一个自建 CA。

Desktop 开远程会话时，把网关地址和密钥发给远程主机。远程主机上的 Claude Code 访问 `https://local-gw:3443`，`local-gw` 在远程主机上解析为它自己的 127.0.0.1，所以请求由远程主机自己的网关处理，不回到本机。

```text
本机会话:   Desktop / Claude Code ─ https://local-gw:3443 ─> caddy          ─> 本机网关 127.0.0.1:3425
远程会话:   Claude Code (远程)    ─ https://local-gw:3443 ─> tls_forward.py ─> 远程网关 127.0.0.1:3425
```
图：同一个网关地址在两台机器上各自指向本机。

远程会话的前提是远程主机上也有一个网关，并且它能访问上游模型服务。

## 2. 目录内容

下表和后文的路径都相对于 `ssh-gateway/` 目录，命令也在这个目录下运行。

| 文件 | 用途 |
|---|---|
| `scripts/gen-certs.sh` | 生成自建 CA 和 `local-gw` 的服务器证书 |
| `mac/Caddyfile` | Mac 上的 HTTPS 反向代理配置，会改写 Host 头 |
| `mac/local-gw-tls.plist` | 让 caddy 开机常驻的 LaunchAgent 模板 |
| `remote/tls_forward.py` | 远程主机上的 HTTPS 转发脚本，只用 Python 标准库 |
| `remote/local-gw-tls.service` | systemd 单元模板 |
| `remote/supervisord.conf` | 没有 systemd 的容器用的 supervisord 配置，启动时补写 `/etc/hosts` |

## 3. 本机（Mac）配置

### 3.1 生成证书

```bash
scripts/gen-certs.sh local-gw ~/.local/share/local-gw
```

脚本生成 4 个文件：`ca.pem`、`ca.key`、`server.pem`、`server.key`。`ca.key` 只留在本机，不要复制到远程主机。

### 3.2 添加主机名

```bash
echo '127.0.0.1 local-gw' | sudo tee -a /etc/hosts
```

### 3.3 信任 CA

```bash
security add-trusted-cert -r trustRoot -p ssl \
  -k ~/Library/Keychains/login.keychain-db ~/.local/share/local-gw/ca.pem
```

运行后，系统会弹窗要求输入登录密码。Desktop 和本机的 Claude Code 都通过钥匙串信任这个 CA。

### 3.4 启动 HTTPS 反向代理

1. 安装 caddy：`brew install caddy`。
2. 复制 `mac/Caddyfile`，把其中的证书路径和网关端口改成你的值。
3. 复制 `mac/local-gw-tls.plist` 到 `~/Library/LaunchAgents/`，把 `/PATH/TO` 改成实际路径。
4. 运行 `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local-gw-tls.plist`。

Mac 上要用 caddy，不能只用纯 TCP 转发。原因是 magpie 这类网关有防 DNS 重绑定的检查：请求带浏览器式的 `User-Agent` 或 `Sec-Fetch-*` 头、Host 又不是 `localhost` 或 `127.0.0.1` 时，网关返回 403。Desktop 主进程基于 Electron，发出的请求带这些头。caddy 把 Host 改成 `127.0.0.1:<端口>`，并删除 `Origin` 和 `X-Forwarded-*`。如果你的网关没有这项检查，也可以在 Mac 上直接用 `remote/tls_forward.py`。

### 3.5 修改 Desktop 配置

3p 模式的配置在 `~/Library/Application Support/Claude-3p/configLibrary/<id>.json`。`_meta.json` 的 `appliedId` 指向当前生效的那份。改之前先备份。

```json
{
  "inferenceProvider": "gateway",
  "inferenceGatewayBaseUrl": "https://local-gw:3443",
  "sshHostAllowlist": ["*"],
  "sshConfigs": [
    {"id": "my-server", "name": "My Server", "sshHost": "user@server.example.com",
     "sshPort": 22, "sshIdentityFile": "~/.ssh/id_ed25519"}
  ]
}
```

- `sshHostAllowlist` 为空时，3p 模式的界面不显示 SSH 入口。`["*"]` 允许所有主机，也可以只列出具体的主机名。
- `sshConfigs` 可选。不写这一项时，也可以在界面里手动添加 SSH 连接。
- 改完后，用 Cmd+Q 完全退出 Desktop 再打开。Desktop 不会自动重新加载配置。

## 4. 远程主机（Linux）配置

1. 把 `ca.pem`、`server.pem`、`server.key` 和 `remote/tls_forward.py` 复制到远程主机，例如放到 `/opt/local-gw/`：

   ```bash
   scp ~/.local/share/local-gw/{ca.pem,server.pem,server.key} remote/tls_forward.py server:/opt/local-gw/
   ```

2. 在远程主机上添加主机名：`echo '127.0.0.1 local-gw' >> /etc/hosts`。
3. 把 CA 装进系统证书库：
   - 在 Debian 或 Ubuntu 上运行 `cp /opt/local-gw/ca.pem /usr/local/share/ca-certificates/local-gw-ca.crt && update-ca-certificates`
   - 在 RHEL 或 Fedora 上运行 `cp /opt/local-gw/ca.pem /etc/pki/ca-trust/source/anchors/local-gw-ca.pem && update-ca-trust`
4. 用 `remote/local-gw-tls.service`（systemd）或 `remote/supervisord.conf`（容器）启动转发。命令中的第二个端口应为远程主机上网关的端口。

远程主机上只用纯 TCP 转发就够了。远程会话的请求由远程主机上的 Claude Code 发出，不带浏览器式请求头，不会触发网关的 403 检查。

在 `~/.claude/settings.json` 的 `env` 中设置 `NODE_EXTRA_CA_CERTS` 无效，Claude Code 仍报 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`。所以远程主机应把 CA 装进系统证书库。

## 5. 验证

本机，模拟 Desktop 的请求头：

```bash
curl -sS https://local-gw:3443/v1/models -H 'Authorization: Bearer x' \
  -H 'User-Agent: Mozilla/5.0 Electron' -H 'Sec-Fetch-Mode: cors' \
  -o /dev/null -w '%{http_code}\n'
```

远程主机，发一条真实请求（把模型名换成你的网关提供的模型）：

```bash
curl -sS https://local-gw:3443/v1/messages -H 'x-api-key: x' \
  -H 'anthropic-version: 2023-06-01' -H 'content-type: application/json' \
  -d '{"model":"<model>","max_tokens":20,"messages":[{"role":"user","content":"hi"}]}' \
  -o /dev/null -w '%{http_code} %{time_total}\n'
```

两条命令的结果都应为 `200`。最后在 Desktop 中选择远程环境，发一条消息，会话顶部应显示 `Started on <主机名>`。

## 6. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `Your provider setup needs a fix`，详情为 `must use https (or http on loopback)` | 网关地址是 http，主机名又不是字面回环地址 | 改用 `https://local-gw:3443` |
| `SSH sessions can't use your model provider settings`，详情为 `that endpoint is this computer` | 网关主机名是回环地址 | 同上 |
| `Couldn't sign in to Gateway`，`/v1/models returned HTTP 403` | 网关拒绝浏览器式请求 | 在 `~/Library/Logs/Claude-3p/main.log` 中看 403 的响应内容；确认 caddy 在运行，并且改写了 Host |
| 证书错误，例如 `UNABLE_TO_VERIFY_LEAF_SIGNATURE` | 这台机器不信任 CA | 本机：检查钥匙串。远程主机：检查系统证书库；容器重建后要重新安装 |
| 远程会话一直显示 `Request failed · Retrying` | 远程主机上的网关访问不到上游模型服务 | 在远程主机上看网关日志，单独测试网关到上游的连接 |
| 本机会话全部失败 | caddy 没有运行，或 `/etc/hosts` 缺少 `local-gw` | 运行 `lsof -nP -iTCP:3443 -sTCP:LISTEN` 检查，用 `launchctl kickstart -k gui/$(id -u)/local-gw-tls` 重启 |

## 7. 维护

- 服务器证书有效期为 800 天。macOS 只信任有效期不超过 825 天的服务器证书。到期前重新运行 `scripts/gen-certs.sh`：脚本会保留已有的 CA，只重新签发服务器证书。然后把新的 `server.pem` 和 `server.key` 复制到远程主机，并重启两台机器上的转发服务。
- 容器重建后，`/etc/hosts` 和系统证书库可能被重置。`remote/supervisord.conf` 会在启动时补写 hosts 条目，CA 要手动重新安装。

## 8. 安全说明

- 两台机器上的转发服务都只监听 `127.0.0.1`，其他机器连不上。
- 自建 CA 能为任何域名签发证书。`ca.key` 应只保存在本机，并限制文件权限。不再使用这套配置时，应从钥匙串和远程主机的系统证书库中删除这个 CA。
- Desktop 会把网关密钥发给远程主机。不要在别人能读取你进程环境的主机上使用重要的密钥。

## License

MIT
