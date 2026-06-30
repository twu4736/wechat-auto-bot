# 微信主播拟人化陪聊工具 🎮💬

一个基于LLM的微信主播拟人化陪聊机器人，支持自动回复、直播通知等功能。

## ✨ 功能特点

- 🤖 **智能对话**: 接入LLM API，实现自然语言对话
- 🎀 **拟人化人设**: 活泼可爱的主播风格，亲切互动
- 📺 **直播通知**: 定时推送直播提醒到指定群聊
- 💬 **指令系统**: 支持查询直播时间、直播间等快捷指令
- 🔒 **黑白名单**: 灵活控制回复对象
- ⏱️ **模拟延迟**: 模拟真人打字节奏
- 🖥️ **Web控制面板**: 浏览器可视化操控，支持登录、开关自动回复、管理直播课表

## 📁 项目结构

```
wechat-auto/
├── config/
│   ├── config.yaml          # 配置文件（需要创建）
│   └── config.example.yaml  # 示例配置
├── src/
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py        # LLM API客户端
│   ├── wechat/
│   │   ├── __init__.py
│   │   └── handler.py       # 微信消息处理
│   ├── livestream/
│   │   ├── __init__.py
│   │   └── notifier.py      # 直播通知管理
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py           # Flask Web控制面板
│   │   ├── templates/
│   │   │   └── index.html   # 控制面板页面
│   │   └── static/
│   │       ├── css/style.css
│   │       └── js/main.js
│   └── utils/
│       ├── __init__.py
│       └── config.py         # 配置加载工具
├── logs/                     # 日志目录（自动创建）
├── main.py                   # 主入口
├── requirements.txt          # 依赖列表
└── README.md                 # 项目说明
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制示例配置文件并修改：

```bash
cp config/config.example.yaml config/config.yaml
```

> 将项目克隆到本地后，通过修改 `config/config.yaml` 即可定制自己的回复逻辑、主播人设与直播排班，无需改动代码。

编辑 `config/config.yaml`，配置以下内容：

```yaml
llm:
  base_url: "https://your-api-url.com/v1"  # LLM API地址
  api_key: "your-api-key"                   # API密钥
  model: "model-name"                       # 模型名称
  system_prompt: |                          # 主播人设提示词
    你是一个活泼可爱的直播主播助手...

livestream:
  room_name: "你的直播间"
  room_url: "https://live.example.com/your-room"
  schedule:
    - day: "周一"
      time: "20:00"
      content: "直播内容描述"
  notify_groups:
    - "群聊名称1"
    - "群聊名称2"
```

### 3. 运行

**Web 控制面板模式（推荐）：**

```bash
python main.py --web
```

浏览器打开 `http://localhost:5000`，在页面上点击"登录微信"扫描二维码，即可通过界面操控机器人。

**CLI 命令行模式：**

```bash
python main.py
```

首次运行会弹出微信登录二维码，扫码登录即可。

**启动参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--web` | 启动Web控制面板模式 | - |
| `--host` | Web服务监听地址 | 0.0.0.0 |
| `--port` | Web服务端口 | 5000 |
| `--config` | 配置文件路径 | config/config.yaml |

## 💬 内置指令

用户发送以下消息会触发特殊回复：

| 指令 | 说明 |
|------|------|
| `直播时间` / `直播安排` | 查看直播时间表 |
| `直播间` / `在哪看直播` | 获取直播间链接 |
| `在直播吗` / `直播状态` | 查询当前直播状态 |
| `重新开始` / `清空记录` | 清空对话历史 |

## ⚙️ 配置说明

### LLM配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `base_url` | API基础地址（兼容OpenAI格式） | - |
| `api_key` | API密钥 | - |
| `model` | 模型名称 | default |
| `temperature` | 温度参数（0-2） | 0.8 |
| `max_tokens` | 最大token数 | 500 |
| `system_prompt` | 系统提示词（主播人设） | - |

> 💡 **推荐模型**：回复模型建议使用 `bytedance/doubao-seed-2.0-mini`，响应快、性价比高，适合做陪聊自动回复。

### 微信配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `auto_login` | 自动登录 | true |
| `hot_reload` | 热缓存登录 | true |
| `reply_delay.min` | 最小回复延迟（秒） | 1 |
| `reply_delay.max` | 最大回复延迟（秒） | 3 |
| `whitelist` | 白名单（空=回复所有人） | [] |
| `blacklist` | 黑名单 | [] |

### 直播通知配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `room_name` | 直播间名称 | - |
| `room_url` | 直播间链接 | - |
| `schedule` | 直播时间表 | [] |
| `notify_groups` | 通知群聊列表 | [] |
| `notify_before` | 提前通知时间（分钟） | 30 |

> 📋 **直播排班格式**：在 `config.yaml` 的 `livestream.schedule` 中配置直播时间，每个条目由 `day`、`time`、`content` 三个字段组成一组，可设置多组，但**不要改变字段格式**。自动回复也会根据这里配置的直播时间及地址来回答粉丝的提问。
>
> ⚠️ **前端课表为临时信息**：Web 控制面板上的「直播表」可以快捷配置，但那只是单次启动系统时的临时信息。**重启系统后会根据 `config.yaml` 重新配置排班直播时间表**，因此请以 `config.yaml` 中的 schedule 为准。

## ⚠️ 注意事项

1. **微信限制**: 使用个人微信可能存在封号风险，建议使用小号
2. **itchat兼容性**: 推荐使用 `itchat-uos` 版本，兼容性更好
3. **网络要求**: 需要能访问LLM API服务
4. **登录状态**: 微信登录后不要在手机上退出，否则会断开连接
5. **群聊需人工**: 自动回复**只能处理单聊，无法检测群聊消息**，群聊消息必须人工回复及推送
6. **推荐模型**: 回复模型建议使用 `bytedance/doubao-seed-2.0-mini`
7. **排班以 config 为准**: 前端 Web 面板的直播表只是单次启动的临时信息，重启后会按 `config.yaml` 重置，请以配置文件为准
8. **本地配置**: 将项目克隆到本地后，通过修改 `config/config.yaml` 定制回复逻辑、人设与直播排班，无需改代码

## 📝 自定义主播人设

修改 `config.yaml` 中的 `system_prompt` 可以自定义主播风格：

```yaml
system_prompt: |
  你是一个幽默搞笑的游戏主播，名叫"大锤"。
  说话风格：
  - 喜欢用网络流行语
  - 经常调侃观众
  - 对游戏非常了解
  - 偶尔装傻卖萌
```

## 🔧 常见问题

### Q: 登录后收不到消息？
A: 检查微信版本，建议使用较旧版本的微信PC端。

### Q: 回复太慢？
A: 调整 `reply_delay` 配置，或检查LLM API响应速度。

### Q: 群聊不回复？
A: 自动回复**只能处理单聊消息，无法检测和回复群聊消息**，这是脚本的能力限制。群聊消息必须人工进行回复及推送，`notify_groups` 仅用于直播开始前的定时提醒推送。

## 📄 许可证

MIT License
