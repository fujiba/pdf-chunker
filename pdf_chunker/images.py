import io
import logging

import pikepdf
from pikepdf import PdfImage
from PIL import Image

logger = logging.getLogger(__name__)


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

        except Exception as e:
            logger.error(f"Failed to optimize {name}: {e}")
