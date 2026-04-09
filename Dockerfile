# ============================================
# Yahoo!ショッピング 最安値スクレイピングアプリ
# GCP Cloud Run 用 Dockerfile
# ============================================

FROM python:3.11-slim

# --- システムパッケージのインストール（Chromium + ChromeDriver）---
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-noto-cjk \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# --- 作業ディレクトリ ---
WORKDIR /app

# --- Pythonパッケージのインストール ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- アプリファイルのコピー ---
# ※ credentials.json はここに含めない（Secret Manager を使用）
COPY app.py .

# --- Streamlit設定ファイルの作成 ---
RUN mkdir -p .streamlit
RUN echo '[server]\nheadless = true\nport = 8080\naddress = "0.0.0.0"\n\n[browser]\ngatherUsageStats = false' \
    > .streamlit/config.toml

# --- ポート公開 ---
EXPOSE 8080

# --- 起動コマンド ---
CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
