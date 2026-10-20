# 线上体验版部署

线上版和本地版使用同一套代码，通过 `AGENTDESK_MODE` 切换。体验版使用服务器密钥、隔离游客内容，每位游客 60 分钟内最多发送 10 次，到期后自动删除临时内容。

建议部署结构：

- 程序：`/opt/creative-partner`
- 临时数据：`/var/lib/creative-partner`
- 私密配置：`/etc/creative-partner.env`
- 服务：`creative-partner.service`
- 端口：`18601`

服务器上的 `/etc/creative-partner.env` 必须只允许管理员读取，真实 API Key 不得写入仓库。安装依赖、构建前端后，将 `creative-partner.service` 放入 `/etc/systemd/system/`，再启动该独立服务即可。
