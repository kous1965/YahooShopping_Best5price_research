# GCP Cloud Run デプロイ手順書
## Yahoo!ショッピング 最安値スクレイピングアプリ

---

## 📁 必要なファイル構成

GitHubリポジトリに以下のファイルを配置してください（credentials.jsonは**含めない**）。

```
YahooSp_Best5price_rsrchGCP/
├── app.py              ← 今回の更新版に差し替え
├── requirements.txt    ← 今回の更新版に差し替え
└── Dockerfile          ← 新規追加
```

---

## STEP 1：GCPプロジェクトの作成

1. [GCPコンソール](https://console.cloud.google.com/) を開く
2. 上部の「プロジェクト選択」▼ をクリック
3. 「新しいプロジェクト」をクリック
4. プロジェクト名を入力（例：`okadaya-yahoo-scraping`）
5. 「作成」をクリック
6. 作成されたプロジェクトの **プロジェクトID** をメモする  
   （例：`okadaya-yahoo-scraping-12345`）

---

## STEP 2：Cloud Shell を開く

GCPコンソール右上の **「>_」アイコン**（Cloud Shellをアクティブにする）をクリックします。  
画面下部にターミナルが開きます。ここにコマンドを貼り付けて実行します。

---

## STEP 3：プロジェクトの設定と必要なAPIの有効化

Cloud Shell で以下を実行します。  
**※ `YOUR_PROJECT_ID` の部分はSTEP 1でメモしたIDに書き換えてください。**

```bash
# プロジェクトを設定
gcloud config set project YOUR_PROJECT_ID

# 必要なAPIを有効化（少し時間がかかります）
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com
```

---

## STEP 4：Artifact Registry（Dockerイメージ保管場所）の作成

```bash
gcloud artifacts repositories create yahoo-scraping \
  --repository-format=docker \
  --location=asia-northeast1 \
  --description="Yahoo scraping app"
```

---

## STEP 5：Secret Manager にシークレットを登録

### 5-1. credentials.json の内容を登録

まず、Codespacesのターミナルで credentials.json の中身を確認します：
```bash
cat credentials.json
```
表示された内容をコピーして、以下の手順で登録します。

**Cloud Shell で実行：**
```bash
# エディタを開いてcredentials.jsonの中身を貼り付ける
nano /tmp/credentials.json
# → 内容を貼り付けて Ctrl+X → Y → Enter で保存

# Secret Manager に登録
gcloud secrets create gcp-service-account \
  --data-file=/tmp/credentials.json
```

### 5-2. ログイン認証情報を登録

**※ `YOUR_USERNAME` と `YOUR_PASSWORD` を実際の値に変えてください。**

```bash
# ユーザー名を登録
echo -n "YOUR_USERNAME" | gcloud secrets create app-username --data-file=-

# パスワードを登録
echo -n "YOUR_PASSWORD" | gcloud secrets create app-password --data-file=-
```

---

## STEP 6：GitHubからソースコードを取得してイメージをビルド

```bash
# リポジトリをクローン
git clone https://github.com/kous1965/YahooSp_Best5price_rsrchGCP.git
cd YahooSp_Best5price_rsrchGCP
```

**⚠️ ここで重要な作業：**  
クローンしたリポジトリの `app.py`、`requirements.txt`、`Dockerfile` を、  
今回作成した新しいファイルに差し替えてください。

```bash
# 差し替えたら、Cloud BuildでDockerイメージをビルド＆プッシュ
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT_ID/yahoo-scraping/app:latest
```

※ ビルドには5〜10分かかります。完了まで待ってください。

---

## STEP 7：Cloud Run にデプロイ

```bash
gcloud run deploy yahoo-scraping \
  --image asia-northeast1-docker.pkg.dev/YOUR_PROJECT_ID/yahoo-scraping/app:latest \
  --region asia-northeast1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --set-secrets GCP_SERVICE_ACCOUNT_JSON=gcp-service-account:latest,APP_USERNAME=app-username:latest,APP_PASSWORD=app-password:latest
```

デプロイが完了すると、以下のようなURLが表示されます：
```
Service URL: https://yahoo-scraping-xxxxxxxxxx-an.a.run.app
```

このURLがアプリのアクセスURLです。ブラウザで開くとログイン画面が表示されます。

---

## STEP 8：動作確認

1. 表示されたURLをブラウザで開く
2. STEP 5-2 で設定したユーザー名・パスワードでログイン
3. JANコードを入力してスクレイピング開始
4. Googleスプレッドシートにデータが転記されることを確認

---

## 💰 料金の目安（月額）

Cloud Runは**使った分だけ課金**なので、使わなければほぼ無料です。

| 項目 | 目安 |
|------|------|
| Cloud Run（処理時間） | 月数十〜数百円程度 |
| Artifact Registry | 月数十円程度 |
| Secret Manager | 月数円程度 |

---

## ⚠️ 注意事項

- `credentials.json` は絶対にGitHubにプッシュしないこと
- パスワードは定期的に変更することを推奨
- スクレイピングは利用規約の範囲内で使用すること

---

## 🔧 よくあるエラーと対処法

**「Permission denied」エラーが出る場合：**
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$(gcloud iam service-accounts list --format='value(email)' | head -1)" \
  --role="roles/secretmanager.secretAccessor"
```

**イメージのビルドが失敗する場合：**
- Dockerfileがリポジトリに含まれているか確認
- Cloud Shell でのディレクトリが正しいか確認（`ls` で確認）

**ログイン後にスプレッドシートエラーが出る場合：**
- `credentials.json` の内容が正確にコピーされているか確認
- GoogleスプレッドシートがService Accountのメールアドレスに共有されているか確認
