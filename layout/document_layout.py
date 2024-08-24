from common.protected_field import *
from layout.block_layout import *

class DocumentLayout:
    def __init__(self, node, frame):
        self.node = node
        self.frame = frame
        node.layout_object = self
        self.parent = None
        self.previous = None
        self.children = []

        self.zoom = ProtectedField(self, "zoom", None, [])
        self.width = ProtectedField(self, "width", None, [])
        self.height = ProtectedField(self, "height")
        self.x = ProtectedField(self, "x", None, [])
        self.y = ProtectedField(self, "y", None, [])

        self.has_dirty_descendants = True

    def layout_needed(self):
        if self.zoom.dirty: return True
        if self.width.dirty: return True
        if self.height.dirty: return True
        if self.x.dirty: return True
        if self.y.dirty: return True
        if self.has_dirty_descendants: return True
        return False
    
    def layout(self, width, zoom):
        if not self.layout_needed(): return

        self.zoom.set(zoom)
        self.width.set(width - 2 * dpx(HSTEP, zoom))

        if not self.children:
            child = BlockLayout(self.node, self, None, self.frame)
            self.height.set_dependencies([child.height])
        else:
            child = self.children[0]
        self.children = [child]

        self.x.set(dpx(HSTEP, zoom))
        self.y.set(dpx(VSTEP, zoom))

        child.layout()
        self.has_dirty_descendants = False

        self.height.copy(child.height)

        for obj in tree_to_list(self, []):
           assert not obj.layout_needed()

    def should_paint(self):
        return True
    
    def paint(self):
        return []
    
    def paint_effects(self, cmds):
        if self.frame != self.frame.tab.root_frame and self.frame.scroll != 0:
            rect = skia.Rect.MakeLTRB(
                self.x.get(), self.y.get(),
                self.x.get() + self.width.get(), self.y.get() + self.height.get())
            cmds = [Transform((0, - self.frame.scroll), rect, self.node, cmds)]
        return cmds