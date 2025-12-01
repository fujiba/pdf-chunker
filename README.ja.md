# pdf_chunker

**LLMフレンドリーなPDF分割＆画像最適化ツール。**

AWS Bedrock (Claude) などのコンテキスト制限やファイルサイズ制限（4.5MB等）を考慮し、RAGの前処理として最適なPDFチャンクを作成します。特に**CMYK画像のRGB変換**やリサイズを自動化し、トークン節約に貢献します。

## 機能 (Features)

* LLM/RAG 最適化:  
  * ファイルサイズ制限の回避: AWS BedrockでのClaude利用時などによくある**4.5MBのファイルサイズ制限**などを、適切なチャンク分割と圧縮によって回避しやすくします。  
  * トークンの節約: 埋め込み画像を視認性を保ったままダウンサンプリングすることで、全体のデータ量を減らし、**トークン消費量とコストを大幅に節約**できます。  
* PDF分割 (Chunking): ファイルサイズ（MB指定）に基づいてPDFを分割します。  
* 画像最適化:  
  * ダウンサンプリング: 埋め込み画像を指定した最大長辺（デフォルト1500px）にリサイズします。  
  * 色空間変換: CMYK画像をRGBに変換し、一部のビューアでの色反転トラブルなどを防ぎます。  
  * 圧縮: JPEG品質を調整してファイルサイズを削減します。  
* コールバック対応: Pythonモジュールとして使用する際、保存処理をフックできるため、S3やデータベースへの直接アップロードが可能です。

## 必要要件

* Python 3.11以上  
* 外部依存: pikepdf が qpdf (ネイティブバイナリ) を必要とします。  
  * macOS: brew install qpdf  
  * Ubuntu/Debian: apt-get install qpdf

## クイックスタート (uv)

```sh
# uvがインストールされている前提  
uv lock  
uv sync

# CLIで実行  
uv run pdf-chunker input.pdf --out-dir output
```

## CLIの使い方

```text
usage: pdf-chunker [-h] [--max-size MAX_SIZE] [--image-max-dim IMAGE_MAX_DIM] input_pdf [output_dir]
```

例:  
10MBごとに分割し、画像は長辺2000pxにリサイズする場合  

```sh
pdf-chunker input.pdf --max-size 10.0 --image-max-dim 2000
```

## 画像解析ツール (pdf-image-dumper)

PDF内部に埋め込まれている画像の情報を検査するためのデバッグツールも同梱されています。解像度や色空間（CMYK/RGB）、フィルタ形式などを一覧表示します。

```sh
pdf-image-dumper input.pdf
```

**出力例:**

```sh
--- Analyzing PDF: input.pdf ---  
 Page |       Name | Width | Height | Size (bytes) | ColorSpace |       Filter | Bits/Comp | APP  
------+------------+-------+--------+--------------+------------+--------------+-----------+-----  
    1 |  /Im1      |  2400 |   3200 |    2,500,123 |  /DeviceCMYK|  /DCTDecode  |         8 | APP14:Adobe  
...
```

## Python APIの使い方

### 基本的な使い方

```python
from pdf_chunker import chunk_pdf

# input.pdf を分割して output ディレクトリに保存  
chunk_pdf(  
    input_path="input.pdf",  
    output_dir="output",  
    max_chunk_size=4 * 1024 * 1024,  # 4MB (バイト指定)  
    image_max_dim=1500               # ピクセル  
)
```

### 応用: コールバックの使用 (S3へのアップロードなど)

save_callback を指定することで、ファイルシステムに保存する代わりに、分割されたPDFオブジェクト（pikepdf.Pdf）を直接受け取って処理できます。

```python
import io  
from pdf_chunker import chunk_pdf

def upload_to_s3(pdf_obj, filename):  
    # pikepdfオブジェクトをバイト列に変換  
    with io.BytesIO() as buffer:  
        pdf_obj.save(buffer)  
        buffer.seek(0)  
          
        # ここで boto3 などを使ってアップロード処理を行います  
        print(f"Uploading {filename} ({len(buffer.getvalue())} bytes) to S3...")  
        # s3.upload_fileobj(buffer, "my-bucket", filename)

chunk_pdf(  
    input_path="large_document.pdf",  
    save_callback=upload_to_s3  
)
```

## Docker / MinIO 連携サンプル

example/ ディレクトリに、MinIO（S3互換ストレージ）と連携する完全なサンプルが含まれています。

* MinIO: PDFファイルがアップロードされるとWebhookイベントを発火します。  
* Callback Server: Webhookを受け取り、PDFをダウンロード・分割し、チャンクをMinIOに書き戻します（ディスクへの中間保存なし）。

**サンプルの実行:**

```sh
cd example  
docker-compose up --build
```

1. MinIOコンソール http://localhost:9001 を開きます (user: minioadmin, pass: minioadmin)。  
2. pdfs バケットにPDFファイルをアップロードします。  
3. サーバーログを確認すると、バケット内の output/ フォルダに分割されたファイル（_part01.pdf など）が生成されます。

## License

MIT License
