# 布灵布灵生成服务

这是静态 GitHub Pages 前端对应的私有单用户后端。它提供人体网格生成、衣物导入任务、
衣物确认、真人参考照和 GPT‑Image‑2 试衣任务接口。

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

生产部署时把 `/data` 替换成私有 GCS/Firestore 适配器，并将密钥放入 Secret Manager。

