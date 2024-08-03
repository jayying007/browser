import socket
import ssl
import tkinter
import tkinter.font
from parser import *
from layout import *
from config import *
from display import *

class URL:
    def __init__(self, url):
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        # Response Status
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        # Response Header
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
        # Response Content
        content = response.read()
        s.close()

        return content
    
    def resolve(self, url):
        if "://" in url: return URL(url)
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/", 1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + \
                       ":" + str(self.port) + url)
        
    def __str__(self):
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        return self.scheme + "://" + self.host + port_part + self.path

class Browser:
    def __init__(self):
        self.tabs = []
        self.active_tab = None

        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window, 
            width=WIDTH,
            height=HEIGHT,
            bg="white"
        )
        self.canvas.pack()

        self.chrome = Chrome(self)

        self.window.bind("<Down>", self.handle_down)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)

    def new_tab(self, url):
        new_tab = Tab(HEIGHT - self.chrome.bottom)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)

        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)

    def handle_down(self, e):
        self.active_tab.scrolldown()
        self.draw()

    def handle_click(self, e):
        if e.y < self.chrome.bottom:
            self.chrome.click(e.x, e.y)
        else:
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.draw()

    def handle_key(self, e):
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return
        self.chrome.keypress(e.char)
        self.draw()

    def handle_enter(self, e):
        self.chrome.enter()
        self.draw()

class Chrome:
    def __init__(self, browser):
        self.browser = browser
        self.focus = None
        self.address_bar = ""

        self.font = get_font(20, "normal", "roman")
        self.font_height = self.font.metrics("linespace")
        # Tab栏
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding

        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
           self.padding, self.padding,
           self.padding + plus_width,
           self.padding + self.font_height)
        # 地址栏
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + \
            self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom

        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding)

        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)
        
    def paint(self):
        cmds = []

        cmds.append(DrawRect(
            Rect(0, 0, WIDTH, self.bottom),
            "white"))
        cmds.append(DrawLine(
            0, self.bottom, WIDTH,
            self.bottom, "black", 1))
        
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+", self.font, "black"))
        # 绘制标签
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left, 0, bounds.left, bounds.bottom,
                "black", 1))
            cmds.append(DrawLine(
                bounds.right, 0, bounds.right, bounds.bottom,
                "black", 1))
            cmds.append(DrawText(
                bounds.left + self.padding, bounds.top + self.padding,
                "Tab {}".format(i), self.font, "black"))
            
            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom, bounds.left, bounds.bottom,
                    "black", 1))
                cmds.append(DrawLine(
                    bounds.right, bounds.bottom, WIDTH, bounds.bottom,
                    "black", 1))
        # 绘制地址栏        
        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, "black"))
        
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                self.address_bar, self.font, "black"))
            
            w = self.font.measure(self.address_bar)
            cmds.append(DrawLine(
                self.address_rect.left + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + self.padding + w,
                self.address_rect.bottom,
                "red", 1))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                url, self.font, "black"))

        return cmds
        
    def tab_rect(self, i):
        tabs_start = self.newtab_rect.right + self.padding
        tab_width = self.font.measure("Tab X") + 2*self.padding
        return Rect(
            tabs_start + tab_width * i, self.tabbar_top,
            tabs_start + tab_width * (i + 1), self.tabbar_bottom)
    
    def click(self, x, y):
        self.focus = None

        if self.newtab_rect.containsPoint(x, y):
            self.browser.new_tab(URL("https://browser.engineering/"))
        elif self.back_rect.containsPoint(x, y):
            self.browser.active_tab.go_back()
        elif self.address_rect.containsPoint(x, y):
            self.focus = "address bar"
            self.address_bar = ""
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).containsPoint(x, y):
                    self.browser.active_tab = tab
                    break
    
    def keypress(self, char):
        if self.focus == "address bar":
            self.address_bar += char

    def enter(self):
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
            self.focus = None

class Tab:
    def __init__(self, tab_height):
        self.url = None

        self.scroll = 0
        self.tab_height = tab_height

        self.history = []
    
    def load(self, url):
        self.history.append(url)
        self.url = url
        body = url.request()
        # Html树
        self.nodes = HTMLParser(body).parse()
        # 解析CSS
        rules = DEFAULT_STYLE_SHEET.copy()

        links = [node.attributes["href"]
                    for node in tree_to_list(self.nodes, [])
                    if isinstance(node, Element)
                    and node.tag == "link"
                    and node.attributes.get("rel") == "stylesheet"
                    and "href" in node.attributes]
        for link in links:
            style_url = url.resolve(link)
            try:
                body = style_url.request()
            except:
                continue
            rules.extend(CSSParser(body).parse())

        style(self.nodes, sorted(rules, key=cascade_priority))
        # 布局树
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        # 绘图
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def draw(self, canvas, offset):
        for cmd in self.display_list:
            # 跳过不可见区域
            if cmd.rect.top > self.scroll + self.tab_height:
                continue
            if cmd.rect.bottom < self.scroll:
                continue

            cmd.execute(self.scroll - offset, canvas)

    def scrolldown(self):
        max_y = max(self.document.height + 2*VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def click(self, x, y):
        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]
        
        if not objs: return
        elt = objs[-1].node

        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elt = elt.parent

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

def style(node, rules):
    node.style = {}

    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value

    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            node.style[property] = value
    # the style attribute should override style sheet values.
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct = float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"
    
    for child in node.children:
        style(child, rules)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

def paint_tree(layout_object, display_list):
    display_list.extend(layout_object.paint())

    for child in layout_object.children:
        paint_tree(child, display_list)

DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()

if __name__ == "__main__":
    import sys
    # body = URL(sys.argv[1]).request()
    # nodes = HTMLParser(body).parse()
    # print_tree(nodes)
    Browser().new_tab(URL(sys.argv[1]))
    tkinter.mainloop()