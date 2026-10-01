"""Avisos experimentales de calidad, sin rechazo automático."""


def assess_quality(image):
    from PIL import ImageStat
    flags = []
    if min(image.size) < 224:
        flags.append("resolución baja; revisar")
    if ImageStat.Stat(image.convert("L")).stddev[0] < 8:
        flags.append("contraste bajo; revisar")
    return {"width": image.width, "height": image.height, "warnings": flags}
