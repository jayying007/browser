import skia

WIDTH, HEIGHT = 800, 600

SCROLL_STEP = 100

HSTEP, VSTEP = 13, 18

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}

REFRESH_RATE_SEC = .033

BROKEN_IMAGE = skia.Image.open("resource/jane.png")

IFRAME_WIDTH_PX = 300
IFRAME_HEIGHT_PX = 150