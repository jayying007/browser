class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent

        self.style = None
        self.animations = {}

        self.is_focused = False
        self.layout_object = None
    
    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent

        self.style = None
        self.animations = {}

        self.is_focused = False
        self.layout_object = None

    def __repr__(self):
        return "<" + self.tag + ">"
    
class AttributeParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def literal(self, literal):
        if self.i < len(self.s) and self.s[self.i] == literal:
            self.i += 1
            return True
        return False

    def word(self, allow_quotes=False):
        start = self.i
        in_quote = False
        quoted = False
        while self.i < len(self.s):
            cur = self.s[self.i]
            if not cur.isspace() and cur not in "=\"\'":
                self.i += 1
            elif allow_quotes and cur in "\"\'":
                in_quote = not in_quote
                quoted = True
                self.i += 1
            elif in_quote and (cur.isspace() or cur == "="):
                self.i += 1
            else:
                break
        if self.i == start:
            self.i = len(self.s)
            return ""
        if quoted:
            return self.s[start+1:self.i-1]
        return self.s[start:self.i]

    def parse(self):
        attributes = {}
        tag = None

        tag = self.word().casefold()
        while self.i < len(self.s):
            self.whitespace()
            key = self.word()
            if self.literal("="):
                value = self.word(allow_quotes=True) 
                attributes[key.casefold()] = value
            else:
                attributes[key.casefold()] = ""
        return (tag, attributes)

class HTMLParser:

    SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ]

    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                if text: self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()
    
    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)

        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)

        if tag.startswith("!"): return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1: return

            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def get_attributes(self, text):
        (tag, attributes) = AttributeParser(text).parse()
        return tag, attributes
    
    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
        
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)

        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)

        return self.unfinished.pop()