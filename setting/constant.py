import skia

WIDTH, HEIGHT = 1600, 900

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

CSS_PROPERTIES = {
    "font-size": "inherit", "font-weight": "inherit",
    "font-style": "inherit", "color": "inherit",
    "opacity": "1.0", "transition": "",
    "transform": "none", "mix-blend-mode": None,
    "border-radius": "0px", "overflow": "visible",
    "outline": "none", "background-color": "transparent",
    "image-rendering": "auto",
}
