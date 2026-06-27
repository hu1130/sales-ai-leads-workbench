# 销售 AI 线索工作台：云端部署与自动上传实施手册

## 一、目标效果

部署完成后，系统从“本机打开”升级为“云端网址访问”：

- 老板/主管：打开网址查看团队看板、线索分配、客户池、资料处理中心。
- 销售：打开网址查看自己负责的客户，也可以上传截图/录音。
- 管理员：接收官网、抖音、小红书、微信等来源线索，并分配给销售。
- 自动上传：销售手机截图/录音同步到销售电脑后，由本机 watcher 自动上传到云端系统。

## 二、推荐上线方式

当前阶段推荐使用一台 Linux 云服务器：

- 2 核 CPU
- 4 GB 内存
- 40 GB 硬盘
- Ubuntu 22.04 / Debian 12
- 安全组开放：80、443、22

正式给销售使用时建议绑定域名并启用 HTTPS。

## 三、云服务器部署

### 1. 上传项目

把整个项目目录上传到服务器，例如：

```bash
/opt/sales-ai
```

服务器上至少需要包含：

```text
deploy/
outputs/sales_ai_frontend/
work/sales_ai_backend/
```

### 2. 安装 Docker

在服务器执行：

```bash
docker --version
docker compose version
```

如果没有安装，需要先安装 Docker 和 Docker Compose。

### 3. 配置生产环境变量

```bash
cd /opt/sales-ai/deploy
cp .env.prod.example .env.prod
nano .env.prod
```

必须修改：

```text
JWT_SECRET_KEY=改成一串很长的随机字符
DEFAULT_ADMIN_PASSWORD=正式管理员密码
```

需要 AI 分析时填写：

```text
DEEPSEEK_API_KEY=你的 DeepSeek Key
DASHSCOPE_API_KEY=你的阿里 DashScope Key
```

如果已经有域名，例如 `https://sales.example.com`，可以把：

```text
CORS_ORIGINS=*
```

改成：

```text
CORS_ORIGINS=https://sales.example.com
```

### 4. 启动系统

```bash
cd /opt/sales-ai/deploy
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f backend
```

访问：

```text
http://服务器公网IP
```

登录：

```text
账号：admin
密码：.env.prod 里的 DEFAULT_ADMIN_PASSWORD
```

## 四、销售端自动上传到云端

这个功能运行在每个销售自己的 Windows 电脑上。

业务链路：

```text
销售手机截图/录音
↓
Syncthing 同步到销售电脑 inbox 文件夹
↓
销售电脑 watcher 自动上传到云端
↓
云端 AI 识别并生成客户/资料记录
↓
主管在团队看板和资料处理中心查看
```

### 1. 配置手机同步

手机 Syncthing 选择要同步的文件夹：

- 微信长截图所在相册/截图目录
- 手机通话录音目录

电脑端接收到项目目录：

```text
work\Automatic-Phone-Recording-main\data\inbox
```

截图可以放：

```text
work\Automatic-Phone-Recording-main\data\inbox\wechat
```

录音可以放：

```text
work\Automatic-Phone-Recording-main\data\inbox\recordings
```

程序会递归扫描 inbox 下的图片和录音。

### 2. 启动销售端自动上传

在销售电脑上双击：

```text
启动销售端自动上传到云端.bat
```

按提示填写：

```text
Cloud site URL: https://你的域名 或 http://服务器公网IP
Admin username: admin
Sales username: 这个销售在系统里的账号，例如 sales01
Admin password: 管理员密码
```

窗口保持打开即可。

### 3. 销售归属规则

`Sales username` 决定资料上传后归属哪个销售。

例如填写：

```text
sales01
```

则这个销售手机同步来的截图/录音，进入云端后会绑定到 `sales01` 名下。

## 五、上线后老板能看到什么

主管/管理员登录后可以看到：

- 工作台：今日优先跟进客户、资料分析进度
- 客户池：所有客户、按销售筛选、查看负责销售
- 资料处理：截图/录音/文档的处理状态
- 线索分配：官网/抖音/小红书/微信来的未分配线索
- 团队看板：每个销售今日新增、今日跟进、今日资料、高意向、未跟进
- 销售账号：创建和维护销售账号

## 六、建议上线顺序

第一阶段，先上线核心系统：

1. 云服务器部署
2. 管理员创建销售账号
3. 销售网页上传截图/录音
4. 管理员分配线索
5. 主管查看团队看板

第二阶段，再启用自动上传：

1. 每个销售手机配置 Syncthing
2. 销售电脑运行自动上传脚本
3. 验证截图/录音是否自动进入云端资料处理中心

第三阶段，优化正式生产：

1. 绑定域名
2. 配置 HTTPS
3. 默认管理员密码改强密码
4. SQLite 升级 PostgreSQL/MySQL
5. 增加定时备份
6. 增加操作日志和权限审计

## 七、常见问题

### 1. 销售打开网址看不到全部客户？

正常。销售账号只能看自己负责的客户。管理员账号可以看全部客户。

### 2. 手机截图没有自动进入系统？

检查三点：

- Syncthing 是否已经把图片同步到电脑 inbox 文件夹
- `启动销售端自动上传到云端.bat` 窗口是否还开着
- `Sales username` 是否填写了系统里真实存在的销售账号

### 3. 资料显示无法判断？

通常是截图内容太少、图片不清楚、DeepSeek/DashScope Key 未配置或 OCR 识别失败。可以先手动编辑客户资料，后续继续优化识别提示词。

### 4. 云端系统需要一直开电脑吗？

不需要。系统运行在云服务器上。销售电脑只在需要自动同步手机截图/录音时保持 watcher 打开。
