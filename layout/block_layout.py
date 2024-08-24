from common.protected_field import *
from layout.iframe_layout import *
from layout.image_layout import *
from layout.input_layout import *
from layout.text_layout import *
from layout.line_layout import *
from parser.html_parser import *

from utils.util import *
from utils.render_util import *

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
        node.layout_object = self
        self.parent = parent
        self.previous = previous
        self.frame = frame

        self.zoom = ProtectedField(self, "zoom", self.parent, [self.parent.zoom])
        self.width = ProtectedField(self, "width", self.parent, [self.parent.width])
        self.height = ProtectedField(self, "height", self.parent)
        self.x = ProtectedField(self, "x", self.parent, [self.parent.x])

        if self.previous:
            y_dependencies = [self.previous.y, self.previous.height]
        else:
            y_dependencies = [self.parent.y]
        self.y = ProtectedField(self, "y", self.parent, y_dependencies)

        self.children = ProtectedField(self, "children", self.parent, None, [])

        self.has_dirty_descendants = True

    def layout_needed(self):
        if self.zoom.dirty: return True
        if self.width.dirty: return True
        if self.height.dirty: return True
        if self.x.dirty: return True
        if self.y.dirty: return True
        if self.children.dirty: return True
        if self.has_dirty_descendants: return True
        return False
    
    def layout(self):
        if not self.layout_needed(): return

        self.zoom.copy(self.parent.zoom)
        self.width.copy(self.parent.width)
        self.x.copy(self.parent.x)

        if self.previous:
            prev_y = self.previous.y.read(notify=self.y)
            prev_height = self.previous.height.read(notify=self.y)
            self.y.set(prev_y + prev_height)
        else:
            self.y.copy(self.parent.y)

        mode = self.layout_mode()
        if mode == "block":
            if self.children.dirty:
                children = []
                previous = None
                for child in self.node.children:
                    next = BlockLayout(child, self, previous, self.frame)
                    children.append(next)
                    previous = next
                self.children.set(children)

                height_dependencies = [child.height for child in children]
                height_dependencies.append(self.children)
                self.height.set_dependencies(height_dependencies)
        else:
            if self.children.dirty:
                self.temp_children = []
                self.new_line()
                self.recurse(self.node)
                self.children.set(self.temp_children)

                height_dependencies = [child.height for child in self.temp_children]
                height_dependencies.append(self.children)
                self.height.set_dependencies(height_dependencies)
                self.temp_children = None

        for child in self.children.get():
            child.layout()

        self.has_dirty_descendants = False

        children = self.children.read(notify=self.height)
        new_height = sum([
            child.height.read(notify=self.height)
            for child in children
        ])
        self.height.set(new_height)

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
        zoom = self.zoom.read(notify=self.children)
        node_font = font(node.style, zoom, notify=self.children)
        w = node_font.measureText(word)
        self.add_inline_child(node, w, TextLayout, self.frame, word)

    def add_inline_child(self, node, w, child_class, frame, word=None):
        width = self.width.read(notify=self.children)
        if self.cursor_x + w > width:
            self.new_line()
        line = self.temp_children[-1]
        if word:
            child = child_class(node, word, line, self.previous_word)
        else:
            child = child_class(node, line, self.previous_word, frame)
        line.children.append(child)
        self.previous_word = child
        zoom = self.zoom.read(notify=self.children)
        self.cursor_x += w + font(node.style, zoom, notify=self.children).measureText(' ')

    def new_line(self):
        self.previous_word = None
        self.cursor_x = 0
        last_line = self.temp_children[-1] \
            if self.temp_children else None
        new_line = LineLayout(self.node, self, last_line)
        self.temp_children.append(new_line)
        
    def image(self, node):
        zoom = self.zoom.read(notify=self.children)
        if 'width' in node.attributes:
            w = dpx(int(node.attributes['width']), zoom)
        else:
            w = dpx(node.image.width(), zoom)
        self.add_inline_child(node, w, ImageLayout, self.frame)

    def input(self, node):
        zoom = self.zoom.read(notify=self.children)
        w = dpx(INPUT_WIDTH_PX, zoom)
        self.add_inline_child(node, w, InputLayout, self.frame)

    def iframe(self, node):
        zoom = self.zoom.read(notify=self.children)
        if 'width' in self.node.attributes:
            w = dpx(int(self.node.attributes['width']), zoom)
        else:
            w = IFRAME_WIDTH_PX + dpx(2, zoom)
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
            else:
                for child in node.children:
                    self.recurse(child)
    
    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x.get(), self.y.get(), self.x.get() + self.width.get(),
            self.y.get() + self.height.get())
    
    def should_paint(self):
        return isinstance(self.node, Text) or \
            (self.node.tag not in ["input", "button", "img", "iframe"])

    def paint(self):
        cmds = []
        bgcolor = self.node.style["background-color"].get()
        if bgcolor != "transparent":
            radius = dpx(float(self.node.style["border-radius"].get()[:-2]), self.zoom.get())
            cmds.append(DrawRRect(self.self_rect(), radius, bgcolor))
        return cmds
    
    def paint_effects(self, cmds):
        if self.node.is_focused \
            and "contenteditable" in self.node.attributes:
            text_nodes = [
                t for t in tree_to_list(self, [])
                if isinstance(t, TextLayout)
            ]
            if text_nodes:
                cmds.append(DrawCursor(text_nodes[-1], text_nodes[-1].width.get()))
            else:
                cmds.append(DrawCursor(self, 0))

        cmds = paint_visual_effects(self.node, cmds, self.self_rect())
        return cmds
    
    def __repr__(self):
        return "BlockLayout(x={}, y={}, width={}, height={}, node={})".format(
            self.x, self.x, self.width, self.height, self.node)