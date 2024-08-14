import math
import urllib.parse
from network import *
from parser import *
from layout import *
from config import *
from display import *
from script import *
from util import *
from task import *
from measure import *

DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()

class Tab:
    def __init__(self, browser, tab_height):
        self.url = None
        self.loaded = False
        # 页面历史
        self.history = []
        
        self.scroll = 0
        self.scroll_changed_in_tab = False
        self.tab_height = tab_height
        # 当前焦点  
        self.focus = None
        self.browser = browser

        self.needs_render = False
        self.js = None
        self.task_runner = TaskRunner(self)
        self.task_runner.start_thread()

    def allowed_request(self, url):
        return self.allowed_origins == None or url.origin() in self.allowed_origins
    
    def load(self, url, payload=None):
        self.loaded = False
        self.scroll = 0
        self.scroll_changed_in_tab = True;

        self.task_runner.clear_pending_tasks()

        self.url = url
        headers, body = url.request(self.url, payload)
        self.history.append(url)
        
        self.allowed_origins = None
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin).origin())
        # Html树
        self.nodes = HTMLParser(body).parse()
        # 解析CSS
        self.rules = DEFAULT_STYLE_SHEET.copy()

        links = [node.attributes["href"]
                    for node in tree_to_list(self.nodes, [])
                    if isinstance(node, Element)
                    and node.tag == "link"
                    and node.attributes.get("rel") == "stylesheet"
                    and "href" in node.attributes]
        for link in links:
            style_url = url.resolve(link)
            if not self.allowed_request(style_url):
                print("Blocked link", link, "due to CSP")
                continue
            try:
                header, body = style_url.request(url)
            except:
                continue
            self.rules.extend(CSSParser(body).parse())
        # 解析JavaScript
        if self.js: self.js.discarded = True
        self.js = JSContext(self)
        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to CSP")
                continue
            try:
                header, body = script_url.request(url)
            except:
                continue
            task = Task(self.js.run, script_url, body)
            self.task_runner.schedule_task(task)
        
        self.set_needs_render()
        self.loaded = True

    ##########################
    # 渲染
    ##########################
    def set_needs_render(self):
        self.needs_render = True
        self.browser.set_needs_animation_frame(self)

    def render(self):
        if not self.needs_render: return
        self.browser.measure.time('render')

        style(self.nodes, sorted(self.rules, key=cascade_priority))
        # 布局树
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        # 绘图
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.needs_render = False
        
        clamped_scroll = self.clamp_scroll(self.scroll)
        if clamped_scroll != self.scroll:
            self.scroll_changed_in_tab = True
        self.scroll = clamped_scroll

        self.browser.measure.stop('render')
    # 这个方法和drawRect差不多
    def run_animation_frame(self, scroll):
        if not self.scroll_changed_in_tab:
            self.scroll = scroll
        self.browser.measure.time('script-runRAFHandlers')
        self.js.interp.evaljs("__runRAFHandlers()")
        self.browser.measure.stop('script-runRAFHandlers')

        self.render()

        scroll = None
        if self.scroll_changed_in_tab:
            scroll = self.scroll
        document_height = math.ceil(self.document.height + 2*VSTEP)
        commit_data = CommitData(self.url, scroll, document_height, self.display_list)
        self.display_list = None
        self.browser.commit(self, commit_data)
        self.scroll_changed_in_tab = False

    def clamp_scroll(self, scroll):
        height = math.ceil(self.document.height + 2*VSTEP)
        maxscroll = height - self.tab_height
        return max(0, min(scroll, maxscroll))

    ##############################
    # 用户事件
    ##############################
    def click(self, x, y):
        # we need to read the layout tree to figure out what object was clicked on,
        # which means the layout tree needs to be up to date.
        self.render()
        self.focus = None

        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]
        if not objs: return

        elt = objs[-1].node
        if elt and self.js.dispatch_event("click", elt): return

        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elif elt.tag == "input":
                elt.attributes["value"] = ""
                if self.focus:
                    self.focus.is_focused = False
                self.focus = elt
                elt.is_focused = True
                self.set_needs_render()
            elif elt.tag == "button":
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
            elt = elt.parent

    def submit_form(self, elt):
        if self.js.dispatch_event("submit", elt): return
        inputs = [node for node in tree_to_list(elt, [])
                  if isinstance(node, Element)
                  and node.tag == "input"
                  and "name" in node.attributes]
        
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            value = urllib.parse.quote(value)
            body += "&" + name + "=" + value
        body = body[1:]

        url = self.url.resolve(elt.attributes["action"])
        self.load(url, body)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def keypress(self, char):
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus): return
            self.focus.attributes["value"] += char
            self.set_needs_render()


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

def paint_tree(layout_object, display_list):
    cmds = []
    if layout_object.should_paint():
        cmds = layout_object.paint()
    for child in layout_object.children:
        paint_tree(child, cmds)

    if layout_object.should_paint():
        cmds = layout_object.paint_effects(cmds)
    display_list.extend(cmds)