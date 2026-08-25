InvalidOperation: 
Line |
   2 |  [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Literal ��
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot set property. Property setting is supported only on core types in this language mode.
# ���鲼�����ɷ���

���Ǿ�̬ GitHub Pages ǰ�˶�Ӧ��˽�е��û���ˡ����ṩ�����������ɡ����ﵼ������
����ȷ�ϡ����˲ο��պ� GPT?Image?2 ��������ӿڡ�

## ��������

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
$env:BLING_OWNER_TOKEN="your-private-code"
$env:BLING_OPENAI_API_KEY="..."
.venv\Scripts\uvicorn app.main:app --reload --port 8080
```

����ȷ����Ȩ�� 3D-Human-Body-Shape Ů��ģ��� RFE ������� `model_data/`��
δ����Ȩ�ػ� OpenAI ��Կʱ�ӿڻ���ȷ���� 503�������˻ؾɵļ������ CSS ��ͼ��

��������ʱ�� `/data` �滻��˽�� GCS/Firestore ��������������Կ���� Secret Manager��


