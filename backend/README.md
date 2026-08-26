# 布灵布灵生成服务

这是静态 GitHub Pages 前端对应的 v3 私有云端后端。它提供 Firebase 匿名身份、GCS
直传、Firestore 衣橱、Cloud Tasks 处理、人体网格和 GPT‑Image‑2 真实试衣。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
$env:BLING_OWNER_TOKEN="your-private-code"
$env:BLING_OPENAI_API_KEY="..."
.venv\Scripts\uvicorn app.main:app --reload --port 8080
```

将已确认授权的 3D-Human-Body-Shape 女性模板和 RFE 矩阵放入 `model_data/`。
未配置权重或 OpenAI 密钥时接口会明确返回 503，不会退回旧的假人体或 CSS 贴图。

## 生产配置

Cloud Run 至少配置以下环境变量：

```text
BLING_FIREBASE_PROJECT_ID=<project-id>
BLING_FIRESTORE_PROJECT_ID=<project-id>
BLING_STORAGE_BUCKET=<private-bucket>
BLING_PUBLIC_BASE_URL=https://<cloud-run-service>
BLING_CLOUD_RUN_SERVICE_URL=https://<cloud-run-service>
BLING_CLOUD_TASKS_PROJECT=<project-id>
BLING_CLOUD_TASKS_LOCATION=<region>
BLING_CLOUD_TASKS_QUEUE=bling-generation
BLING_CLOUD_TASKS_SECRET=<Secret Manager 注入>
BLING_OPENAI_API_KEY=<Secret Manager 注入>
```

GCS bucket 只允许 Cloud Run 服务账号访问；浏览器通过 30 分钟签名地址上传和读取。
为 bucket 配置允许 `https://axiyea-jpg.github.io` 的 `PUT`/`GET` CORS。Firestore 数据位于
`users/{firebaseUid}/garments|jobs|references`，接口不会接受客户端传入的 user id。

把 Cloud Run URL 和 Firebase Web 配置写入 `assets/bling-config.js`。这些值不是密钥；
OpenAI key、任务密钥和服务账号凭据禁止进入前端或 GitHub。

没有完成 Firebase、GCS、Firestore、Cloud Tasks、模型参考图和 OpenAI 密钥配置时，
前端会明确显示“云端衣橱尚未部署”，不会回退到 localStorage、雪碧图或伪试衣。
