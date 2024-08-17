import skia
from util import *
from parser import *

def is_focusable(node):
    if get_tabindex(node) < 0:
        return False
    elif "tabindex" in node.attributes:
        return True
    else:
        return node.tag in ["input", "button", "a"]

def get_tabindex(node):
    tabindex = int(node.attributes.get("tabindex", "9999999"))
    return 9999999 if tabindex == 0 else tabindex

class AccessibilityNode:
    def __init__(self, node):
        self.node = node
        self.children = []
        self.text = ""
        self.bounds = self.compute_bounds()

        if isinstance(node, Text):
            if is_focusable(node.parent):
                self.role = "focusable text"
            else:
                self.role = "StaticText"
        else:
            if "role" in node.attributes:
                self.role = node.attributes["role"]
            elif node.tag == "a":
                self.role = "link"
            elif node.tag == "input":
                self.role = "textbox"
            elif node.tag == "button":
                self.role = "button"
            elif node.tag == "html":
                self.role = "document"
            elif is_focusable(node):
                self.role = "focusable"
            else:
                self.role = "none"

    def compute_bounds(self):
        if self.node.layout_object:
            return [absolute_bounds_for_obj(self.node.layout_object)]
        if isinstance(self.node, Text):
            return []
        inline = self.node.parent
        bounds = []
        while not inline.layout_object: inline = inline.parent
        for line in inline.layout_object.children:
            line_bounds = skia.Rect.MakeEmpty()
            for child in line.children:
                if child.node.parent == self.node:
                    line_bounds.join(skia.Rect.MakeXYWH(
                        child.x, child.y, child.width, child.height))
            bounds.append(line_bounds)
        return bounds

    def build(self):
        for child_node in self.node.children:
            self.build_internal(child_node)

        if self.role == "StaticText":
            self.text = repr(self.node.text)
        elif self.role == "focusable text":
            self.text = "Focusable text: " + self.node.text
        elif self.role == "focusable":
            self.text = "Focusable element"
        elif self.role == "textbox":
            if "value" in self.node.attributes:
                value = self.node.attributes["value"]
            elif self.node.tag != "input" and self.node.children and \
                 isinstance(self.node.children[0], Text):
                value = self.node.children[0].text
            else:
                value = ""
            self.text = "Input box: " + value
        elif self.role == "button":
            self.text = "Button"
        elif self.role == "link":
            self.text = "Link"
        elif self.role == "alert":
            self.text = "Alert"
        elif self.role == "document":
            self.text = "Document"

        if self.node.is_focused:
            self.text += " is focused"

    def build_internal(self, child_node):
        child = AccessibilityNode(child_node)
        if child.role != "none":
            self.children.append(child)
            child.build()
        else:
            for grandchild_node in child_node.children:
                self.build_internal(grandchild_node)

    def contains_point(self, x, y):
        for bound in self.bounds:
            if bound.contains(x, y):
                return True
        return False

    def hit_test(self, x, y):
        node = None
        if self.contains_point(x, y):
            node = self
        for child in self.children:
            res = child.hit_test(x, y)
            if res: node = res
        return node

    def __repr__(self):
        return "AccessibilityNode(node={} role={} text={} bounds={}".format(
            str(self.node), self.role, self.text, self.bounds)