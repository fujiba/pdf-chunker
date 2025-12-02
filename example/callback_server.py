import io
import logging
import os
import tempfile
from urllib.parse import unquote_plus

import boto3
from fastapi import FastAPI, HTTPException, Request

from pdf_chunker import chunk_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI()

# --- MinIO Configuration ---
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

s3_client = boto3.client(
    "s3",
    endpoint_url=f"http://{MINIO_ENDPOINT}",
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    config=boto3.session.Config(signature_version="s3v4"),
)


@app.get("/health")
def health_check():
    """
    Health check endpoint for Docker.
    """
    return {"status": "ok"}


@app.post("/events")
async def handle_minio_event(request: Request):
    """
    Endpoint to receive webhook notifications from MinIO.
    """
    try:
        event = await request.json()
    except Exception:
        logging.error("Failed to parse request JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logging.info(f"Received event: {event}")

    for record in event.get("Records", []):
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = unquote_plus(record["s3"]["object"]["key"])

        logging.info(f"Processing s3://{bucket_name}/{object_key}")

        # 無限ループ防止: object_keyに 'output/' が含まれていたら処理をスキップ
        if "output/" in object_key:
            logging.info(f"Skipping already processed file: {object_key}")
            continue

        try:
            process_pdf_from_minio(bucket_name, object_key)
        except Exception as e:
            logging.error(f"Failed to process {object_key}: {e}")

    return {"status": "ok"}


def process_pdf_from_minio(bucket_name, object_key):
    """
    Downloads a PDF from MinIO, chunks it, and uploads the parts back to MinIO.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        input_path = tmp_file.name

    try:
        logging.info(f"Downloading {object_key} to {input_path}")
        s3_client.download_file(bucket_name, object_key, input_path)

        # Define the save_callback function for uploading chunks
        def upload_chunk_to_minio(pdf_obj, filename):
            """
            Callback to save a chunked PDF object to MinIO instead of disk.
            """
            # 元のファイル名から拡張子を除いた部分を取得
            base, _ = os.path.splitext(os.path.basename(object_key))

            # pdf-chunkerが生成したファイル名から "_partXX" の部分を抽出
            # 例: "tmpXXXX_part01.pdf" -> "_part01"
            part_suffix = ""
            if "_part" in filename:
                part_suffix = "_" + filename.split("_part")[-1].split(".")[0]

            # 新しいファイル名を組み立てる: "元のファイル名_partXX.pdf"
            new_filename = f"{base}{part_suffix}.pdf"
            output_key = os.path.join("output", new_filename)

            with io.BytesIO() as pdf_bytes:
                pdf_obj.save(pdf_bytes)
                pdf_bytes.seek(0)

                logging.info(f"Uploading chunk to s3://{bucket_name}/{output_key}")
                s3_client.upload_fileobj(pdf_bytes, bucket_name, output_key)

        # Run the chunker with the callback
        chunk_pdf(
            input_path=input_path,
            save_callback=upload_chunk_to_minio,
        )

    finally:
        # Clean up the temporary file
        if os.path.exists(input_path):
            os.remove(input_path)
            logging.info(f"Cleaned up temporary file: {input_path}")
