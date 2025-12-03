import io
import logging

import pikepdf
from pikepdf import PdfImage
from PIL import Image

logger = logging.getLogger(__name__)


def is_type0_font_broken(font) -> bool:
    """
    Type0フォントのDescendantFontsが壊れてるか検証。

    NotebookLM等で生成されたPDFでは、DescendantFontsが正しいCIDFont辞書ではなく、
    画像オブジェクト、FontFileストリーム、ページオブジェクト等への
    不正な参照になっていることがある。

    Args:
        font: pikepdf フォントオブジェクト

    Returns:
        True: フォントが壊れている（削除すべき）
        False: 正常、またはType0以外
    """
    # Type0以外は対象外
    if font.get("/Subtype") != pikepdf.Name.Type0:
        return False

    desc = font.get("/DescendantFonts")

    # DescendantFontsがない
    if desc is None:
        return True

    # 配列でない
    if not hasattr(desc, "__iter__"):
        return True

    for d in desc:
        # Noneが入ってる
        if d is None:
            return True

        # 辞書/オブジェクトでない
        if not hasattr(d, "get"):
            return True

        subtype = d.get("/Subtype")

        # 正常なCIDFontは /CIDFontType0 か /CIDFontType2 で /BaseFont必須
        if subtype in [pikepdf.Name.CIDFontType0, pikepdf.Name.CIDFontType2]:
            if d.get("/BaseFont") is not None:
                continue  # 正常
            else:
                return True  # BaseFontがないのは壊れてる

        # FontFile3のSubtype（フォントデータStreamであってCIDFont辞書ではない）
        if subtype == pikepdf.Name("/CIDFontType0C"):
            return True

        # 画像オブジェクトが混入
        if subtype == pikepdf.Name.Image:
            return True

        # TrueTypeフォントが混入（Type0のDescendantFontsにTrueTypeは来ない）
        if subtype == pikepdf.Name.TrueType:
            return True

        # Type0の二重ネスト
        if subtype == pikepdf.Name.Type0:
            return True

        dtype = d.get("/Type")

        # ページオブジェクトが混入
        if dtype == pikepdf.Name.Page:
            return True

        # XObjectが混入
        if dtype == pikepdf.Name.XObject:
            return True

        # Info辞書が混入
        if "/CreationDate" in d or "/ModDate" in d or "/Producer" in d:
            return True

        # FontFile Streamっぽい（/Filter + /Length があって /BaseFont がない）
        if "/Filter" in d and "/Length" in d and "/BaseFont" not in d:
            return True

        # DescendantFontsの二重ネスト
        if "/DescendantFonts" in d:
            return True

        # Subtypeがなく、CIDFontに必要なキーもない
        if subtype is None:
            if "/CIDSystemInfo" not in d and "/W" not in d and "/BaseFont" not in d:
                return True

    return False


def remove_broken_fonts(page) -> int:
    """
    ページから壊れたType0フォントを削除する。

    Args:
        page: pikepdf ページオブジェクト

    Returns:
        削除したフォントの数
    """
    fonts = page.Resources.get("/Font", {})
    if not hasattr(fonts, "keys"):
        return 0

    broken_fonts = [
        fname for fname, font in fonts.items() if is_type0_font_broken(font)
    ]

    for fname in broken_fonts:
        logger.info(f"Removing broken font: {fname}")
        del fonts[fname]

    return len(broken_fonts)


def optimize_image(pikepdf_image, quality=60, max_dim=1500):
    """
    Optimize a pikepdf image object (resize, convert CMYK->RGB, compress).
    Returns JPEG bytes and size/mode.
    If the image is already optimal (RGB/JPEG and small enough), returns original bytes.
    """
    raw_data = pikepdf_image.obj.read_raw_bytes()
    current_filter = pikepdf_image.obj.get("/Filter")

    has_adobe, transform = has_adobe_app14_marker(raw_data)
    logger.debug(f"Adobe APP14: {has_adobe}, transform: {transform}")

    pil_image = pikepdf_image.as_pil_image()

    is_modified = False

    if pil_image.mode == "CMYK":
        if needs_inversion(pikepdf_image):
            pil_image = pil_image.point(lambda x: 255 - x)
        pil_image = pil_image.convert("RGB")
        is_modified = True

    width, height = pil_image.size

    if max_dim and max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        new_size = (int(width * scale), int(height * scale))
        pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)
        is_modified = True

    if pil_image.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        pil_image_rgba = pil_image.convert("RGBA")
        background.paste(pil_image_rgba, mask=pil_image_rgba.split()[3])
        pil_image = background
        is_modified = True
    elif pil_image.mode not in ("RGB", "CMYK"):
        pil_image = pil_image.convert("RGB")
        is_modified = True

    if not is_modified and current_filter == pikepdf.Name.DCTDecode:
        logger.debug("Image is already RGB/JPEG and small enough. Returning original.")
        return raw_data, pil_image.width, pil_image.height, pil_image.mode

    img_byte_arr = io.BytesIO()
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
    adobe_marker = b"\xff\xee"
    idx = jpeg_data.find(adobe_marker)
    if idx == -1:
        return False, None
    start = idx + 4
    if jpeg_data[start : start + 5] == b"Adobe":
        transform = jpeg_data[start + 11] if len(jpeg_data) > start + 11 else None
        return True, transform
    return False, None


def needs_inversion(pikepdf_image):
    if pikepdf_image.obj.get("/Filter") != pikepdf.Name.DCTDecode:
        return False
    raw_data = pikepdf_image.obj.read_raw_bytes()
    has_adobe, transform = has_adobe_app14_marker(raw_data)
    return has_adobe and transform in (0, 2)


def process_page_images(pdf_doc, page, max_dim=1500):
    """Compress images found on a page and replace them in-place."""
    for name, image_obj in page.images.items():
        try:
            logger.debug(f"Processing image: {name}")

            image_filter = image_obj.get("/Filter")
            if image_filter not in (pikepdf.Name.DCTDecode, pikepdf.Name.FlateDecode):
                logger.warning(
                    f"Skipping unsupported image format: {name} (Filter: {image_filter})"
                )
                continue

            p_img = PdfImage(image_obj)

            logger.info(
                f"Optimizing image: {name} ({p_img.width}x{p_img.height} -> max {max_dim})"
            )
            new_data, w, h, final_mode = optimize_image(
                p_img, quality=75, max_dim=max_dim
            )

            image_obj.write(new_data)
            image_obj.Width = w
            image_obj.Height = h
            image_obj.Filter = pikepdf.Name.DCTDecode
            image_obj.ColorSpace = pikepdf.Name.DeviceRGB
            image_obj.BitsPerComponent = 8

            if "/Decode" in image_obj:
                del image_obj.Decode
            if "/DecodeParms" in image_obj:
                del image_obj.DecodeParms

            remove_broken_fonts(page)

        except Exception as e:
            logger.error(f"Failed to optimize {name}: {e}")
