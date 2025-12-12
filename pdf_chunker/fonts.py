import logging

import pikepdf

logger = logging.getLogger(__name__)

# 壊れたType0フォントのSubtypeとしてよくあるもの
BROKEN_SUBTYPES = {
    pikepdf.Name("/CIDFontType0C"),  # FontFile3
    pikepdf.Name.Image,
    pikepdf.Name.TrueType,
    pikepdf.Name.Type0,  # Nested Type0
}


def is_type0_font_broken(font: "pikepdf.Dictionary") -> bool:
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

        # 不正なSubtypeをチェック
        if subtype in BROKEN_SUBTYPES:
            return True

        dtype = d.get("/Type")

        # ページオブジェクト、XObjectが混入
        if dtype in {pikepdf.Name.Page, pikepdf.Name.XObject}:
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


def remove_broken_fonts(page: "pikepdf.Page") -> int:
    """
    ページから壊れたType0フォントを削除する。

    Args:
        page: pikepdf ページオブジェクト

    Returns:
        削除したフォントの数
    """
    # リソース、フォントがない場合はスキップ
    if "/Resources" not in page:
        return 0

    fonts = page.Resources.get("/Font", {})

    broken_fonts = [
        fname for fname, font in fonts.items() if is_type0_font_broken(font)
    ]

    for fname in broken_fonts:
        logger.info(f"Removing broken font: {fname}")
        del fonts[fname]

    return len(broken_fonts)
