# pdf_chunker

**LLM-friendly PDF splitting & image optimization tool.**

Designed to prepare documents for RAG and LLM context windows (e.g., AWS Bedrock, Claude) by handling chunking, **CMYK to RGB conversion**, and smart image resizing.

## Features

* LLM Optimized:  
  * Bypass File Size Limit*: Helps fit PDFs within strict constraints, such as the **4.5MB file size limit** often encountered when using models like Claude on AWS Bedrock.  
  * Token Efficiency: Downsampling embedded images reduces the overall data payload while preserving necessary visual information, leading to significant savings in **token usage and costs**.  
* PDF Chunking: Splits PDFs based on file size (specified in MB).  
* Image Optimization:  
  * Downsampling: Resizes embedded images to a specified maximum dimension (default: 1500px).  
  * Color Conversion: Converts CMYK images to RGB to prevent display issues (e.g., inverted colors).  
  * Compression: Adjusts JPEG quality to reduce file size.  
* Callback Support: Hook into the saving process via a callback for direct uploads to S3, databases, etc., without saving chunks to local disk.

## Requirements

* Python 3.11+  
* External Dependencies: qpdf (native binary) is required by pikepdf.  
  * macOS: brew install qpdf  
  * Ubuntu/Debian: apt-get install qpdf

## Quickstart (uv)

```sh
# ensure uv is installed  
uv lock  
uv sync

# Run via CLI  
uv run pdf-chunker input.pdf --out-dir output
```

## CLI Usage

```sh
usage: pdf-chunker [-h] [--max-size MAX_SIZE] [--image-max-dim IMAGE_MAX_DIM] input_pdf [output_dir]

Split large PDFs into smaller chunks

positional arguments:  
  input_pdf             Input PDF file path  
  output_dir            Output directory (optional, defaults to source dir)

options:  
  -h, --help            show this help message and exit  
  --max-size MAX_SIZE   Max chunk size in MB (default: 4.0)  
  --image-max-dim IMAGE_MAX_DIM  
                        Max dimension for images in pixels (default: 1500)
```

Example:  
Split into 10MB chunks and resize images to 2000px on the longest side.  

```sh
pdf-chunker input.pdf --max-size 10.0 --image-max-dim 2000
```

## Image Analysis Tool (pdf-image-dumper)

A debugging tool is included to inspect images embedded within a PDF. It lists details such as resolution, color space (CMYK/RGB), and filters.

```sh
pdf-image-dumper input.pdf
```

**Output Example:**

```sh
--- Analyzing PDF: input.pdf ---  
 Page |       Name | Width | Height | Size (bytes) | ColorSpace |       Filter | Bits/Comp | APP  
------+------------+-------+--------+--------------+------------+--------------+-----------+-----  
    1 |  /Im1      |  2400 |   3200 |    2,500,123 |  /DeviceCMYK|  /DCTDecode  |         8 | APP14:Adobe  
...
```

## Python API Usage

### Basic Usage

```python
from pdf_chunker import chunk_pdf

# Split input.pdf into chunks in the 'output' directory  
chunk_pdf(  
    input_path="input.pdf",  
    output_dir="output",  
    max_chunk_size=4 * 1024 * 1024,  # 4MB (bytes)  
    image_max_dim=1500               # pixels  
)
```

### Advanced: Using Callbacks (e.g., Upload to S3)

By providing a save_callback, you can receive the split PDF objects (pikepdf.Pdf) directly instead of saving them to the file system.

```python
import io  
from pdf_chunker import chunk_pdf

def upload_to_s3(pdf_obj, filename):  
    # Convert pikepdf object to bytes  
    with io.BytesIO() as buffer:  
        pdf_obj.save(buffer)  
        buffer.seek(0)  
          
        # Here you would use boto3 or similar to upload  
        print(f"Uploading {filename} ({len(buffer.getvalue())} bytes) to S3...")  
        # s3.upload_fileobj(buffer, "my-bucket", filename)

chunk_pdf(  
    input_path="large_document.pdf",  
    save_callback=upload_to_s3  
)
```

## Docker / MinIO Integration Example

The example/ directory contains a complete example of integration with MinIO (S3-compatible storage).

* MinIO: Triggers a webhook event when a PDF file is uploaded.  
* Callback Server: Receives the webhook, downloads the PDF, chunks it, and uploads the parts back to MinIO (without intermediate disk storage).

**Run the example:**

```sh
cd example  
docker-compose up --build
```

1. Open MinIO Console at http://localhost:9001 (user: minioadmin, pass: minioadmin).  
2. Upload a PDF to the pdfs bucket.  
3. Check the server logs; chunked files (_part01.pdf, etc.) will appear in the output/ folder within the bucket.

## License

MIT License