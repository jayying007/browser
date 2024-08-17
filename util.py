import skia
from parser import parse_transform

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

def add_parent_pointers(nodes, parent=None):
    for node in nodes:
        node.parent = parent
        add_parent_pointers(node.children, node)

def print_composited_layers(composited_layers):
    print("Composited layers:")
    for layer in composited_layers:
        print("  " * 4 + str(layer))

NAMED_COLORS = {
    "black": "#000000",
    "gray":  "#808080",
    "white": "#ffffff",
    "red":   "#ff0000",
    "green": "#00ff00",
    "blue":  "#0000ff",
    "lightblue": "#add8e6",
    "lightgreen": "#90ee90",
    "orange": "#ffa500",
    "orangered": "#ff4500",
}

def parse_color(color):
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return skia.Color(r, g, b)
    elif color.startswith("#") and len(color) == 9:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        a = int(color[7:9], 16)
        return skia.Color(r, g, b, a)
    elif color in NAMED_COLORS:
        return parse_color(NAMED_COLORS[color])
    else:
        return skia.ColorBLACK
    
def parse_blend_mode(blend_mode_str):
    if blend_mode_str == "multiply":
        return skia.BlendMode.kMultiply
    elif blend_mode_str == "difference":
        return skia.BlendMode.kDifference
    elif blend_mode_str == "destination-in":
        return skia.BlendMode.kDstIn
    elif blend_mode_str == "source-over":
        return skia.BlendMode.kSrcOver
    else:
        return skia.BlendMode.kSrcOver
    
def linespace(font):
    metrics = font.getMetrics()
    return metrics.fDescent - metrics.fAscent

def map_translation(rect, translation, reversed=False):
    if not translation:
        return rect
    else:
        (x, y) = translation
        matrix = skia.Matrix()
        if reversed:
            matrix.setTranslate(-x, -y)
        else:
            matrix.setTranslate(x, y)
        return matrix.mapRect(rect)
    
def absolute_bounds_for_obj(obj):
    rect = skia.Rect.MakeXYWH(
        obj.x, obj.y, obj.width, obj.height)
    cur = obj.node
    while cur:
        rect = map_translation(rect,
            parse_transform(
                cur.style.get("transform", "")))
        cur = cur.parent
    return rect

def local_to_absolute(display_item, rect):
    while display_item.parent:
        rect = display_item.parent.map(rect)
        display_item = display_item.parent
    return rect

def absolute_to_local(display_item, rect):
    parent_chain = []
    while display_item.parent:
        parent_chain.append(display_item.parent)
        display_item = display_item.parent
    for parent in reversed(parent_chain):
        rect = parent.unmap(rect)
    return rect

def dpx(css_px, zoom):
    return css_px * zoom

def parse_image_rendering(quality):
    if int(skia.__version__.split(".")[0]) > 87:
        if quality == "high-quality":
            return skia.SamplingOptions(skia.CubicResampler.Mitchell())
        elif quality == "crisp-edges":
            return skia.SamplingOptions(
                skia.FilterMode.kNearest, skia.MipmapMode.kNone)
        else:
            return skia.SamplingOptions(
                skia.FilterMode.kLinear, skia.MipmapMode.kLinear)

    if quality == "high-quality":
        return skia.FilterQuality.kHigh_FilterQuality
    elif quality == "crisp-edges":
        return skia.FilterQuality.kLow_FilterQuality
    else:
        return skia.FilterQuality.kMedium_FilterQuality