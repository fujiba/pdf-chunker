import io
import os
import sys

import pikepdf
from pikepdf import Pdf, PdfImage
from PIL import Image

# 4.0MB 制限 (少し余裕を持たせる)
MAX_CHUNK_SIZE = 4.0 * 1024 * 1024


def compress_image(pikepdf_image, quality=60, max_dim=1500):
    """
    pikepdfの画像オブジェクトを受け取り、Pillowで圧縮して
    新しいpikepdf用の画像オブジェクト（の元データ）を返す
    """
    raw_data = pikepdf_image.obj.read_raw_bytes()

    has_adobe, transform = has_adobe_app14_marker(raw_data)
    print(f"    Adobe APP14: {has_adobe}, transform: {transform}")

    # Pillow画像に変換
    pil_image = pikepdf_image.as_pil_image()

    if pil_image.mode == "CMYK":
        if needs_inversion(pikepdf_image):
            pil_image = pil_image.point(lambda x: 255 - x)
        pil_image = pil_image.convert("RGB")

    # 1. リサイズ (長辺を指定サイズに抑える)
    width, height = pil_image.size
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        new_size = (int(width * scale), int(height * scale))
        pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)

    # 2. JPEG変換 & 圧縮
    # 透過情報を持つモード(RGBA, LA, P)の場合、白背景と合成してRGBに変換
    if pil_image.mode in ("RGBA", "P", "LA"):
        # 白背景と合成
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        # 透過マスクを使って合成
        pil_image_rgba = pil_image.convert("RGBA")
        background.paste(pil_image_rgba, mask=pil_image_rgba.split()[3])
        pil_image = background
    # CMYKでもRGBでもない他のモード（例: L(グレースケール)）をRGBに変換
    elif pil_image.mode not in ("RGB", "CMYK"):
        pil_image = pil_image.convert("RGB")

    # バッファにJPEGとして書き出し
    img_byte_arr = io.BytesIO()
    # ICCプロファイルが存在すれば、それを維持して保存する
    icc_profile = pil_image.info.get("icc_profile")
    if pil_image.mode == "CMYK":
        pil_image.save(
            img_byte_arr,
            format="JPEG",
            quality=quality,
            subsampling=0,
            icc_profile=icc_profile,
        )
    else:
        pil_image.save(
            img_byte_arr, format="JPEG", quality=quality, icc_profile=icc_profile
        )

    return img_byte_arr.getvalue(), pil_image.width, pil_image.height, pil_image.mode


def has_adobe_app14_marker(jpeg_data):
    """
    JPEGデータにAdobe APP14マーカーがあるかチェック
    APP14マーカー: 0xFFEE で始まって 'Adobe' の文字列を含む
    """
    # Adobe APP14 の signature を探す
    # FF EE (APP14) + length(2bytes) + 'Adobe'
    adobe_marker = b"\xff\xee"
    idx = jpeg_data.find(adobe_marker)
    if idx == -1:
        return False, None

    # マーカーの後ろに 'Adobe' があるか
    # 長さ(2バイト)の後に 'Adobe' (5バイト)
    start = idx + 4  # FF EE + 2bytes length
    if jpeg_data[start : start + 5] == b"Adobe":
        # transform フラグは 'Adobe' の11バイト後
        transform = jpeg_data[start + 11] if len(jpeg_data) > start + 11 else None
        return True, transform
    return False, None


def needs_inversion(pikepdf_image):
    """
    Adobe APP14マーカー付きCMYK JPEGかどうか判定
    """
    # JPEGじゃなければ反転不要
    if pikepdf_image.obj.get("/Filter") != pikepdf.Name.DCTDecode:
        return False

    raw_data = pikepdf_image.obj.read_raw_bytes()
    has_adobe, transform = has_adobe_app14_marker(raw_data)

    # Adobe APP14があって transform が 0 か 2 なら反転必要
    return has_adobe and transform in (0, 2)


def process_page_images(pdf_doc, page):
    """
    ページ内の画像を圧縮して置換する
    """
    # ページ内の画像リソース名を取得
    # pikepdfのimages辞書は {名前: 画像オブジェクト} へのアクセサ
    for name, image_obj in page.images.items():
        try:
            print(f"    All keys: {list(image_obj.keys())}")
            print(f"    Raw obj: {image_obj}")
            # 画像の圧縮形式（フィルタ）を取得
            image_filter = image_obj.get("/Filter")
            # /DCTDecode (JPEG) と /FlateDecode (PNG/ZIP) 以外は非対応としてスキップ
            if image_filter not in (pikepdf.Name.DCTDecode, pikepdf.Name.FlateDecode):
                print(
                    f"  ! Skipping unsupported image format: {name} (Filter: {image_filter})"
                )
                continue

            p_img = PdfImage(image_obj)

            print(f"  - Compressing image: {name} ({p_img.width}x{p_img.height})")

            # 圧縮処理
            new_data, w, h, final_mode = compress_image(p_img, quality=75)

            # 圧縮後の画像で元の画像オブジェクトを更新
            image_obj.write(new_data)
            image_obj.Width = w
            image_obj.Height = h
            image_obj.Filter = pikepdf.Name.DCTDecode
            image_obj.ColorSpace = pikepdf.Name.DeviceRGB  # 常にRGB
            image_obj.BitsPerComponent = 8

            # CMYK関連の補正パラメータはすべて不要になるので削除
            if "/Decode" in image_obj:
                del image_obj.Decode
            if "/DecodeParms" in image_obj:
                del image_obj.DecodeParms

        except Exception as e:
            print(f"  ! Failed to compress {name}: {e}")


def get_pdf_size(pdf_obj):
    """メモリ上に書き出してサイズを測る"""
    temp = io.BytesIO()
    pdf_obj.save(temp)
    return temp.tell()


def chunk_pdf(input_path, output_dir=None):
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        return False

    # 出力ディレクトリが指定されていない場合は、入力ファイルと同じディレクトリに設定
    if output_dir is None:
        output_dir = os.path.dirname(input_path)
        # カレントディレクトリのファイルの場合、dirnameは空文字列を返す
        if not output_dir:
            output_dir = "."

    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)

    src_pdf = Pdf.open(input_path)
    base_name, ext = os.path.splitext(os.path.basename(input_path))

    current_chunk = Pdf.new()
    # メタデータなどをコピーしたければここで src_pdf からコピーする

    chunk_count = 1

    print(f"Processing: {input_path} ({len(src_pdf.pages)} pages)")

    # ページループ
    # ※ enumerateを使うとインデックス管理が楽
    # ※ src_pdf.pagesをイテレートする際、src_pdfを開いたままにする必要がある

    # イテレータを手動で回すスタイル（バックトラックが必要なため）
    pages = src_pdf.pages
    i = 0
    total_pages = len(pages)

    while i < total_pages:
        page = pages[i]

        # 現在のチャンクに追加してみる
        current_chunk.pages.append(page)

        # サイズチェック
        current_size = get_pdf_size(current_chunk)

        if current_size > MAX_CHUNK_SIZE:
            # --- サイズオーバー ---
            print(
                f"  [Limit Reached] Chunk size: {current_size / 1024 / 1024:.2f}MB at Page {i + 1}"
            )

            if len(current_chunk.pages) > 1:
                # パターンA: 複数ページある -> 最後のページ(今回足した分)を削除して確定
                del current_chunk.pages[-1]

                # 保存
                output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
                output_name = os.path.join(output_dir, output_filename)
                current_chunk.save(output_name)
                print(f"  -> Saved: {output_name}")

                chunk_count += 1
                current_chunk = Pdf.new()

                # ページiはまだ処理できていないので、インクリメントせずループ先頭へ戻る
                # (つまり、新しいチャンクの先頭としてページiを再トライ)
                continue

            else:
                # パターンB: 1ページだけでデカい -> 画像圧縮を発動
                print(
                    f"  [Compressing] Page {i + 1} is single & huge. Downsampling images..."
                )

                # current_chunkに入っている唯一のページ(page i)の画像を圧縮
                # ※注: src_pdfのページを直接弄ると元データが変わるので、
                # pikepdfでは追加した時点でコピー的な挙動になるが、
                # 念の為 current_chunk 側のページを操作する
                target_page = current_chunk.pages[0]
                process_page_images(current_chunk, target_page)

                # 圧縮後のサイズチェック
                compressed_size = get_pdf_size(current_chunk)
                print(f"  -> Compressed size: {compressed_size / 1024 / 1024:.2f}MB")

                # 圧縮してもサイズ上限を超える場合はエラー終了
                if compressed_size > MAX_CHUNK_SIZE:
                    print(
                        f"  [Error] Failed to compress the page under the size limit ({MAX_CHUNK_SIZE / 1024 / 1024:.2f}MB)."
                    )
                    print("  Aborting process for this file.")
                    return False  # このファイルの処理を中断し、失敗を返す

                output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
                output_name = os.path.join(output_dir, output_filename)
                current_chunk.save(output_name)
                print(f"  -> Saved (Compressed): {output_name}")

                chunk_count += 1
                current_chunk = Pdf.new()
                i += 1  # 次のページへ
        else:
            # サイズ内なら次へ
            i += 1

    # 残りの保存
    if len(current_chunk.pages) > 0:
        output_filename = f"{base_name}_part{chunk_count:02d}{ext}"
        output_name = os.path.join(output_dir, output_filename)
        current_chunk.save(output_name)
        print(f"  -> Saved (Final): {output_name}")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python pdf_chunker.py <input_pdf> [output_directory]")
    else:
        input_file = sys.argv[1]
        output_directory = None
        if len(sys.argv) == 3:
            output_directory = sys.argv[2]
        success = chunk_pdf(input_file, output_directory)
        if not success:
            sys.exit(1)
