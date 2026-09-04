# 布灵布灵本地衣橱服务

本地版使用 FastAPI、SQLite 和设备文件目录保存衣物。图片不会写入浏览器 `localStorage`，
也不会把分类图标或旧雪碧图当作衣物缩略图。

## 一键启动

在 `source` 目录双击 `启动布灵本地版.bat`。首次启动会创建 `.venv`、安装基础依赖，
随后打开 <http://127.0.0.1:8765>。基础 CPU 抠图、裁剪、审核、标签编辑和衣橱管理
不需要付费 API。

数据默认保存在 `source/data/`：SQLite 保存元数据，`garments/{garmentId}/` 保存原图、
透明图、暖白底图与缩略图。访问 `/api/system/status` 可查看各本地能力状态。

## 可选本地模型

- 视觉模型放入 `model_data/vision/` 后启用结构化衣物识别；否则使用离线启发式识别并标记低置信度字段。
- Qwen Image Edit 放入 `model_data/qwen-image-edit/`，并安装 `requirements-ai.txt`。
- 只有检测到 CUDA、至少 12GB 显存、模型和 AI 依赖时才启用 AI 重建；无 GPU 不影响基础流程。

## 商品页助手

`tools/bling-product-page-helper.user.js` 只读取用户当前已打开且有权访问的淘宝、拼多多或
小红书页面可见内容，并发送到本机服务；不会绕过登录、验证码或反爬机制。
