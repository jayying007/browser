from parser import *
from config import *
from display import *
from util import *

# 字体缓存
FONTS = {}
def get_font(size, weight, style):
    key = (weight, style)
    if key not in FONTS:
        if weight == "bold":
            skia_weight = skia.FontStyle.kBold_Weight
        else:
            skia_weight = skia.FontStyle.kNormal_Weight
        if style == "italic":
            skia_style = skia.FontStyle.kItalic_Slant
        else:
            skia_style = skia.FontStyle.kUpright_Slant
        skia_width = skia.FontStyle.kNormal_Width
        style_info = \
            skia.FontStyle(skia_weight, skia_width, skia_style)
        font = skia.Typeface('Arial', style_info)
        FONTS[key] = font
    return skia.Font(FONTS[key], size)

def font(style, zoom):
    weight = style["font-weight"]
    variant = style["font-style"]
    size = None
    try:
        size = float(style["font-size"][:-2]) * 0.75
    except:
        size = 16
    font_size = dpx(size, zoom)
    return get_font(font_size, weight, variant)

class DocumentLayout:
    def __init__(self, node, frame):
        self.node = node
        self.frame = frame
        node.layout_object = self
        self.parent = None
        self.previous = None
        self.children = []

    def layout(self, width, zoom):
        self.zoom = zoom
        child = BlockLayout(self.node, self, None, self.frame)
        self.children.append(child)

        self.width = width - 2 * dpx(HSTEP, self.zoom)
        self.x = dpx(HSTEP, self.zoom)
        self.y = dpx(VSTEP, self.zoom)
        child.layout()
        self.height = child.height

    def should_paint(self):
        return True
    
    def paint(self):
        return []
    
    def paint_effects(self, cmds):
        if self.frame != self.frame.tab.root_frame and self.frame.scroll != 0:
            rect = skia.Rect.MakeLTRB(
                self.x, self.y,
                self.x + self.width, self.y + self.height)
            cmds = [Transform((0, - self.frame.scroll), rect, self.node, cmds)]
        return cmds

BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"
]

class BlockLayout:
    def __init__(self, node, parent, previous, frame):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        node.layout_object = self

        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.frame = frame

    def layout(self):
        self.zoom = self.parent.zoom
        self.x = self.parent.x
        self.width = self.parent.width
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous, self.frame)
                self.children.append(next)
                previous = next
        else:
            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()

        self.height = sum([child.height for child in self.children])

    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif self.node.children:
            for child in self.node.children:
                if isinstance(child, Text): continue
                if child.tag in BLOCK_ELEMENTS:
                    return "block"
            return "inline"
        elif self.node.tag in ["input", "img", "iframe"]:
            return "inline"
        else:
            return "block"

    def word(self, node, word):
        node_font = font(node.style, self.zoom)
        w = node_font.measureText(word)
        self.add_inline_child(node, w, TextLayout, self.frame, word)

    def new_line(self):
        self.cursor_x = self.x
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def add_inline_child(self, node, w, child_class, frame, word=None):
        if self.cursor_x + w > self.x + self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        if word:
            child = child_class(node, word, line, previous_word)
        else:
            child = child_class(node, line, previous_word, frame)
        line.children.append(child)
        self.cursor_x += w + \
            font(node.style, self.zoom).measureText(" ")
        
    def image(self, node):
        if "width" in node.attributes:
            w = dpx(int(node.attributes["width"]), self.zoom)
        else:
            w = dpx(node.image.width(), self.zoom)
        self.add_inline_child(node, w, ImageLayout, self.frame)

    def input(self, node):
        w = dpx(INPUT_WIDTH_PX, self.zoom)
        self.add_inline_child(node, w, InputLayout, self.frame)

    def iframe(self, node):
        if "width" in self.node.attributes:
            w = dpx(int(self.node.attributes["width"]),
                    self.zoom)
        else:
            w = IFRAME_WIDTH_PX + dpx(2, self.zoom)
        self.add_inline_child(node, w, IframeLayout, self.frame) 
     
    def recurse(self, node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            elif node.tag == "img":
                self.image(node)
            elif node.tag == "iframe" and "src" in node.attributes:
                self.iframe(node)
            for child in node.children:
                self.recurse(child)
    
    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x, self.y,
            self.x + self.width, self.y + self.height)
    
    def should_paint(self):
        return isinstance(self.node, Text) or \
            (self.node.tag not in \
                ["input", "button", "img", "iframe"])

    def paint(self):
        cmds = []

        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            radius = dpx(
                float(self.node.style.get("border-radius", "0px")[:-2]),
                    self.zoom)
            cmds.append(DrawRRect(
                self.self_rect(), radius, bgcolor))

        return cmds
    
    def paint_effects(self, cmds):
        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        return cmds
    
    def __repr__(self):
        return "BlockLayout(x={}, y={}, width={}, height={}, node={})".format(
            self.x, self.x, self.width, self.height, self.node)
    
class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

    def layout(self):
        self.zoom = self.parent.zoom
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        if not self.children:
            self.height = 0
            return
        
        max_ascent = max([-child.ascent 
                          for child in self.children])
        baseline = self.y + max_ascent

        for child in self.children:
            if isinstance(child, TextLayout):
                child.y = baseline + child.ascent / 1.25
            else:
                child.y = baseline + child.ascent
        max_descent = max([child.descent
                           for child in self.children])
        self.height = max_ascent + max_descent

    def should_paint(self):
        return True
    
    def paint(self):
        return []
    
    def paint_effects(self, cmds):
        outline_rect = skia.Rect.MakeEmpty()
        outline_node = None
        for child in self.children:
            outline_str = child.node.parent.style.get("outline")
            if parse_outline(outline_str):
                outline_rect.join(child.self_rect())
                outline_node = child.node.parent

        if outline_node:
            paint_outline(
                outline_node, cmds, outline_rect, self.zoom)

        return cmds

class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous

    def layout(self):
        self.zoom = self.parent.zoom
        self.font = font(self.node.style, self.zoom)

        # Do not set self.y!!!
        self.width = self.font.measureText(self.word)

        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x =self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

        self.ascent = self.font.getMetrics().fAscent * 1.25
        self.descent = self.font.getMetrics().fDescent * 1.25

    def should_paint(self):
        return True
    
    def paint(self):
        cmds = []
        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, self.word, self.font, color))
        return cmds
    
    def paint_effects(self, cmds):
        return cmds
    
    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x, self.y, self.x + self.width,
            self.y + self.height)

class EmbedLayout:
    def __init__(self, node, parent, previous, frame):
        self.node = node
        self.frame = frame
        node.layout_object = self
        self.children = []
        self.parent = parent
        self.previous = previous
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.font = None

    def layout(self):
        self.zoom = self.parent.zoom
        self.font = font(self.node.style, self.zoom)
        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = \
                self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

    def should_paint(self):
        return True

INPUT_WIDTH_PX = 200
class InputLayout(EmbedLayout):
    def __init__(self, node, parent, previous, frame):
        super().__init__(node, parent, previous, frame)

    def layout(self):
        super().layout()
        self.width = dpx(INPUT_WIDTH_PX, self.zoom)
        self.height = linespace(self.font)
        self.ascent = -self.height
        self.descent = 0

    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x, self.y, self.x + self.width,
            self.y + self.height)

    def should_paint(self):
        return True

    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color",
                                      "transparent")
        if bgcolor != "transparent":
            radius = dpx(
                float(self.node.style.get("border-radius", "0px")[:-2]),
                self.zoom)
            cmds.append(DrawRRect(self.self_rect(), radius, bgcolor))
        
        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and \
               isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                print("Ignoring HTML contents inside button")
                text = ""
        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        # 绘制光标
        if self.node.is_focused and self.node.tag == "input":
            cx = self.x + self.font.measureText(text)
            cmds.append(DrawLine(
                cx, self.y, cx, self.y + self.height, "black", 1))
        
        return cmds
    
    def paint_effects(self, cmds):
        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        paint_outline(self.node, cmds, self.self_rect(), self.zoom)
        return cmds
    
    def __repr__(self):
        return "InputLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

class ImageLayout(EmbedLayout):
    def __init__(self, node, parent, previous, frame):
        super().__init__(node, parent, previous, frame)

    def layout(self):
        super().layout()

        width_attr = self.node.attributes.get("width")
        height_attr = self.node.attributes.get("height")
        image_width = self.node.image.width()
        image_height = self.node.image.height()
        aspect_ratio = image_width / image_height

        if width_attr and height_attr:
            self.width = dpx(int(width_attr), self.zoom)
            self.img_height = dpx(int(height_attr), self.zoom)
        elif width_attr:
            self.width = dpx(int(width_attr), self.zoom)
            self.img_height = self.width / aspect_ratio
        elif height_attr:
            self.img_height = dpx(int(height_attr), self.zoom)
            self.width = self.img_height * aspect_ratio
        else:
            self.width = dpx(image_width, self.zoom)
            self.img_height = dpx(image_height, self.zoom)

        self.height = max(self.img_height, linespace(self.font))

        self.ascent = -self.height
        self.descent = 0

    def paint(self):
        cmds = []
        rect = skia.Rect.MakeLTRB(
            self.x, self.y + self.height - self.img_height,
            self.x + self.width, self.y + self.height)
        quality = self.node.style.get("image-rendering", "auto")
        cmds.append(DrawImage(self.node.image, rect, quality))
        return cmds

    def paint_effects(self, cmds):
        return cmds

    def __repr__(self):
        return ("ImageLayout(src={}, x={}, y={}, width={}," +
            "height={})").format(self.node.attributes["src"],
                self.x, self.y, self.width, self.height)

IFRAME_WIDTH_PX = 300
IFRAME_HEIGHT_PX = 150

class IframeLayout(EmbedLayout):
    def __init__(self, node, parent, previous, parent_frame):
        super().__init__(node, parent, previous, parent_frame)

    def layout(self):
        super().layout()

        width_attr = self.node.attributes.get("width")
        height_attr = self.node.attributes.get("height")

        if width_attr:
            self.width = dpx(int(width_attr) + 2, self.zoom)
        else:
            self.width = dpx(IFRAME_WIDTH_PX + 2, self.zoom)

        if height_attr:
            self.height = dpx(int(height_attr) + 2, self.zoom)
        else:
            self.height = dpx(IFRAME_HEIGHT_PX + 2, self.zoom)

        if self.node.frame and self.node.frame.loaded:
            self.node.frame.frame_height = \
                self.height - dpx(2, self.zoom)
            self.node.frame.frame_width = \
                self.width - dpx(2, self.zoom)

        self.ascent = -self.height
        self.descent = 0

    def paint(self):
        cmds = []

        rect = skia.Rect.MakeLTRB(
            self.x, self.y,
            self.x + self.width, self.y + self.height)
        bgcolor = self.node.style.get("background-color",
            "transparent")
        if bgcolor != "transparent":
            radius = dpx(float(
                self.node.style.get("border-radius", "0px")[:-2]),
                self.zoom)
            cmds.append(DrawRRect(rect, radius, bgcolor))
        return cmds

    def paint_effects(self, cmds):
        rect = skia.Rect.MakeLTRB(
            self.x, self.y,
            self.x + self.width, self.y + self.height)
        diff = dpx(1, self.zoom)
        offset = (self.x + diff, self.y + diff)
        cmds = [Transform(offset, rect, self.node, cmds)]
        inner_rect = skia.Rect.MakeLTRB(
            self.x + diff, self.y + diff,
            self.x + self.width - diff, self.y + self.height - diff)
        internal_cmds = cmds
        internal_cmds.append(Blend(1.0, "destination-in", None, [
                          DrawRRect(inner_rect, 0, "white")]))
        cmds = [Blend(1.0, "source-over", self.node, internal_cmds)]
        paint_outline(self.node, cmds, rect, self.zoom)
        cmds = paint_visual_effects(self.node, cmds, rect)
        return cmds

    def __repr__(self):
        return "IframeLayout(src={}, x={}, y={}, width={}, height={})".format(
            self.node.attributes["src"], self.x, self.y, self.width, self.height)

def paint_outline(node, cmds, rect, zoom):
    outline = parse_outline(node.style.get("outline"))
    if not outline: return
    thickness, color = outline
    cmds.append(DrawOutline(rect, color, dpx(thickness, zoom)))

def parse_outline(outline_str):
    if not outline_str: return None
    values = outline_str.split(" ")
    if len(values) != 3: return None
    if values[1] != "solid": return None
    return int(values[0][:-2]), values[2]

def paint_visual_effects(node, cmds, rect):
    opacity = float(node.style.get("opacity", "1.0"))
    blend_mode = node.style.get("mix-blend-mode")
    translation = parse_transform(
        node.style.get("transform", ""))

    if node.style.get("overflow", "visible") == "clip":
        border_radius = float(node.style.get("border-radius", "0px")[:-2])
        if not blend_mode:
            blend_mode = "source-over"
        cmds.append(Blend(1.0, "destination-in", None, [
            DrawRRect(rect, border_radius, "white")
        ]))

    blend_op = Blend(opacity, blend_mode, node, cmds)
    node.blend_op = blend_op
    return [Transform(translation, rect, node, [blend_op])]