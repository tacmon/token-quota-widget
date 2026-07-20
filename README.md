# Token Quota Widget

[English](README.en.md) | 简体中文

![Token Quota Widget](docs/widget.png)

一个面向 Quota Share API 的极简 Linux 桌面悬浮组件。窗口无标题栏、始终置顶、支持拖动和透明度调节，显示：

- 7 天额度的已用、剩余和重置时间
- 近 72 小时的总 Token 消耗
- 输入、输出、缓存读取 Token 和请求数（悬停 Token 行查看）
- 可在设置中切换中文或英文界面

应用只使用 Python 标准库与 Tk，不需要安装第三方 Python 包。

## 运行

要求 Python 3.11+ 和 Tk 8.6。在项目目录执行：

```bash
python3 -m token_quota_widget
```

也可以先用演示数据检查界面，不会访问网络：

```bash
python3 -m token_quota_widget --demo
```

## 安装到桌面

```bash
git clone https://github.com/tacmon/token-quota-widget.git
cd token-quota-widget
chmod +x install.sh uninstall.sh
./install.sh
```

安装后可从应用菜单启动“Token 额度”。需要登录桌面后自动启动时：

```bash
./install.sh --autostart
```

卸载程序文件：

```bash
./uninstall.sh
```

## API Key

Key 按以下顺序获取：

1. 环境变量 `QUOTA_SHARE_API_KEY`
2. 当前 `~/.codex/config.toml` 对应的 `~/.codex/auth.json`
3. 设置窗口中手动填写

自动读取 Codex Key 前，程序会检查当前 provider 的 `base_url` 与额度接口是否同域。这样不会把 OpenAI 或其他 provider 的 Key 发给错误的服务。手动填写的 Key 只保留在本次进程内；应用配置不会保存 Key。

请求固定使用 `Authorization: Bearer ...` 头，Key 不会进入 URL。若 Codex 鉴权文件权限过宽，设置窗口会显示警告；可以修正为：

```bash
chmod 600 ~/.codex/auth.json
```

## 刷新规则

- `mode=light`：默认每 15 秒查询一次，可在设置中调整为 5 到 300 秒
- `mode=full`：每 65 秒查询一次，并限制手动刷新频率，用于更新近 72 小时 Token

这两个间隔均低于服务端的 30 次/分钟和 3 次/分钟限制。累计历史仍需在网页查询。

## 界面语言

点击齿轮打开设置，在“界面语言 / Language”中选择 `中文` 或 `English` 后保存。语言选择与透明度、刷新间隔和窗口位置一起保存在应用配置中，不涉及 API Key。

## 数据说明

“剩余额度”直接使用接口 `rate_limits.remaining` 及其单位；当前服务返回 USD。“近 72 小时 Token”使用完整接口的 `usage.total_tokens`，其中包括接口统计的输入、输出、缓存创建和缓存读取 Token。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT
