import io

import pikepdf
from pikepdf import PdfImage
from PIL import Image


def compress_image(pikepdf_image, quality=60, max_dim=1500):
    """
    Compress a pikepdf image object using Pillow and return JPEG bytes and size/mode.
    """
    raw_data = pikepdf_image.obj.read_raw_bytes()

    has_adobe, transform = has_adobe_app14_marker(raw_data)
    print(f"    Adobe APP14: {has_adobe}, transform: {transform}")

    pil_image = pikepdf_image.as_pil_image()

    if pil_image.mode == "CMYK":
        if needs_inversion(pikepdf_image):
            pil_image = pil_image.point(lambda x: 255 - x)
        pil_image = pil_image.convert("RGB")

    width, height = pil_image.size
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        new_size = (int(width * scale), int(height * scale))
        pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)

    if pil_image.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        pil_image_rgba = pil_image.convert("RGBA")
        background.paste(pil_image_rgba, mask=pil_image_rgba.split()[3])
        pil_image = background
    elif pil_image.mode not in ("RGB", "CMYK"):
        pil_image = pil_image.convert("RGB")

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


def process_page_images(pdf_doc, page):
    """Compress images found on a page and replace them in-place."""
    for name, image_obj in page.images.items():
        try:
            print(f"    All keys: {list(image_obj.keys())}")
            print(f"    Raw obj: {image_obj}")
            image_filter = image_obj.get("/Filter")
            if image_filter not in (pikepdf.Name.DCTDecode, pikepdf.Name.FlateDecode):
                print(
                    f"  ! Skipping unsupported image format: {name} (Filter: {image_filter})"
                )
                continue

            p_img = PdfImage(image_obj)
            print(f"  - Compressing image: {name} ({p_img.width}x{p_img.height})")
            new_data, w, h, final_mode = compress_image(p_img, quality=75)

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
            print(f"  ! Failed to compress {name}: {e}")
