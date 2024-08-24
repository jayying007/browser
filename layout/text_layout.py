from common.protected_field import *
from utils.render_util import *

class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous

        self.zoom = ProtectedField(self, "zoom", self.parent,
            [self.parent.zoom])
        self.font = ProtectedField(self, "font", self.parent,
            [self.zoom,
             self.node.style['font-weight'],
             self.node.style['font-style'],
             self.node.style['font-size']])
        self.width = ProtectedField(self, "width", self.parent,
            [self.font])
        self.height = ProtectedField(self, "height", self.parent,
            [self.font])
        self.ascent = ProtectedField(self, "ascent", self.parent,
            [self.font])
        self.descent = ProtectedField(self, "descent", self.parent,
            [self.font])
        if self.previous:
            x_dependencies = [self.previous.x, self.previous.font,
            self.previous.width]
        else:
            x_dependencies = [self.parent.x]
        self.x = ProtectedField(self, "x", self.parent,
            x_dependencies)
        self.y = ProtectedField(self, "y", self.parent,
            [self.ascent, self.parent.y, self.parent.ascent])

        self.has_dirty_descendants = True

    def layout_needed(self):
        if self.zoom.dirty: return True
        if self.width.dirty: return True
        if self.height.dirty: return True
        if self.x.dirty: return True
        if self.y.dirty: return True
        if self.ascent.dirty: return True
        if self.descent.dirty: return True
        if self.font.dirty: return True
        if self.has_dirty_descendants: return True
        return False

    def layout(self):
        if not self.layout_needed(): return

        self.zoom.copy(self.parent.zoom)

        zoom = self.zoom.read(notify=self.font)
        self.font.set(font(self.node.style, zoom, notify=self.font))

        f = self.font.read(notify=self.width)
        self.width.set(f.measureText(self.word))

        f = self.font.read(notify=self.ascent)
        self.ascent.set(f.getMetrics().fAscent * 1.25)

        f = self.font.read(notify=self.descent)
        self.descent.set(f.getMetrics().fDescent * 1.25)

        f = self.font.read(notify=self.height)
        self.height.set(linespace(f) * 1.25)

        if self.previous:
            prev_x = self.previous.x.read(notify=self.x)
            prev_font = self.previous.font.read(notify=self.x)
            prev_width = self.previous.width.read(notify=self.x)
            self.x.set(
                prev_x + prev_font.measureText(' ') + prev_width)
        else:
            self.x.copy(self.parent.x)

        self.has_dirty_descendants = False

    def should_paint(self):
        return True
    
    def paint(self):
        cmds = []
        leading = self.height.get() / 1.25 * .25 / 2
        color = self.node.style['color'].get()
        cmds.append(DrawText(
            self.x.get(), self.y.get() + leading,
            self.word, self.font.get(), color))
        return cmds
    
    def paint_effects(self, cmds):
        return cmds
    
    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x.get(), self.y.get(), self.x.get() + self.width.get(),
            self.y.get() + self.height.get())