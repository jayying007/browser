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
from accessibility import *

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
        self.zoom = 1
        self.needs_focus_scroll = False
        # 当前焦点  
        self.focus = None
        self.browser = browser
        self.dark_mode = browser.dark_mode

        self.needs_style = False
        self.needs_layout = False
        self.needs_paint = False

        self.needs_accessibility = False
        self.accessibility_tree = None
        
        self.js = None
        self.task_runner = TaskRunner(self)
        self.task_runner.start_thread()

        self.composited_updates = []

    def allowed_request(self, url):
        return self.allowed_origins == None or url.origin() in self.allowed_origins
    
    def load(self, url, payload=None):
        self.loaded = False
        self.scroll = 0
        self.scroll_changed_in_tab = True;
        self.zoom = 1
        self.focus_element(None)
        self.accessibility_tree = None

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
        self.needs_style = True
        self.browser.set_needs_animation_frame(self)

    def set_needs_layout(self):
        self.needs_layout = True
        self.browser.set_needs_animation_frame(self)

    def set_needs_paint(self):
        self.needs_paint = True
        self.browser.set_needs_animation_frame(self)

    def render(self):
        self.browser.measure.time('render')

        if self.needs_style:
            if self.dark_mode:
                INHERITED_PROPERTIES["color"] = "white"
            else:
                INHERITED_PROPERTIES["color"] = "black"
            style(self.nodes, sorted(self.rules, key=cascade_priority), self)
            self.needs_layout = True
            self.needs_style = False
        # 布局树
        if self.needs_layout:
            self.document = DocumentLayout(self.nodes)
            self.document.layout(self.zoom)
            self.needs_accessibility = True
            self.needs_paint = True
            self.needs_layout = False
        if self.needs_accessibility:
            self.accessibility_tree = AccessibilityNode(self.nodes)
            self.accessibility_tree.build()
            self.needs_accessibility = False
        # 绘图
        if self.needs_paint:
            self.display_list = []
            paint_tree(self.document, self.display_list)
            self.needs_paint = False
        
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

        for node in tree_to_list(self.nodes, []):
            for (property_name, animation) in \
                node.animations.items():
                value = animation.animate()
                if value:
                    node.style[property_name] = value
                    self.composited_updates.append(node)
                    self.set_needs_paint()

        needs_composite = self.needs_style or self.needs_layout

        self.render()

        if self.needs_focus_scroll and self.focus:
            self.scroll_to(self.focus)
        self.needs_focus_scroll = False

        scroll = None
        if self.scroll_changed_in_tab:
            scroll = self.scroll

        composited_updates = None
        if not needs_composite:
            composited_updates = {}
            for node in self.composited_updates:
                composited_updates[node] = node.blend_op
        self.composited_updates = []

        document_height = math.ceil(self.document.height + 2*VSTEP)
        commit_data = CommitData(
            self.url, scroll, document_height, self.display_list,
            composited_updates,
            self.accessibility_tree,
            self.focus)
        self.display_list = None
        self.scroll_changed_in_tab = False
        self.accessibility_tree = None

        self.browser.commit(self, commit_data)

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
        self.focus_element(None)

        y += self.scroll
        loc_rect = skia.Rect.MakeXYWH(x, y, 1, 1)
        objs = [obj for obj in tree_to_list(self.document, [])
                if absolute_bounds_for_obj(obj).intersects(
                    loc_rect)]
        if not objs: return

        elt = objs[-1].node
        if elt and self.js.dispatch_event("click", elt): return

        while elt:
            if isinstance(elt, Text):
                pass
            elif is_focusable(elt):
                self.focus_element(elt)
                self.activate_element(elt)
                return
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
        if self.focus and self.focus.tag == "input":
            if not "value" in self.focus.attributes:
                self.activate_element(self.focus)
            if self.js.dispatch_event("keydown", self.focus): return
            self.focus.attributes["value"] += char
            self.set_needs_render()

    def zoom_by(self, increment):
        if increment:
            self.zoom *= 1.1
            self.scroll *= 1.1
        else:
            self.zoom *= 1/1.1
            self.scroll *= 1/1.1
        self.scroll_changed_in_tab = True
        self.set_needs_render()

    def reset_zoom(self):
        self.scroll /= self.zoom
        self.zoom = 1
        self.scroll_changed_in_tab = True
        self.set_needs_render()

    def set_dark_mode(self, val):
        self.dark_mode = val
        self.set_needs_render()

    def advance_tab(self):
        focusable_nodes = [node
            for node in tree_to_list(self.nodes, [])
            if isinstance(node, Element) and is_focusable(node)]
        focusable_nodes.sort(key=get_tabindex)

        if self.focus in focusable_nodes:
            idx = focusable_nodes.index(self.focus) + 1
        else:
            idx = 0

        if idx < len(focusable_nodes):
            self.focus_element(focusable_nodes[idx])
            self.browser.focus_content()
        else:
            self.focus_element(None)
            self.browser.focus_addressbar()
        self.set_needs_render()

    def enter(self):
        if not self.focus: return
        if self.js.dispatch_event("click", self.focus): return
        self.activate_element(self.focus)

    def activate_element(self, elt):
        if elt.tag == "input":
            elt.attributes["value"] = ""
            self.set_needs_render()
        elif elt.tag == "a" and "href" in elt.attributes:
            url = self.url.resolve(elt.attributes["href"])
            self.load(url)
        elif elt.tag == "button":
            while elt:
                if elt.tag == "form" and "action" in elt.attributes:
                    self.submit_form(elt)
                    return
                elt = elt.parent

    def focus_element(self, node):
        if node and node != self.focus:
            self.needs_focus_scroll = True
        if self.focus:
            self.focus.is_focused = False
        self.focus = node
        if node:
            node.is_focused = True
        self.set_needs_render()

    def scroll_to(self, elt):
        assert not (self.needs_style or self.needs_layout)
        objs = [
            obj for obj in tree_to_list(self.document, [])
            if obj.node == self.focus
        ]
        if not objs: return
        obj = objs[0]

        if self.scroll < obj.y < self.scroll + self.tab_height:
            return

        document_height = math.ceil(self.document.height + 2*VSTEP)
        new_scroll = obj.y - SCROLL_STEP
        self.scroll = self.clamp_scroll(new_scroll)
        self.scroll_changed_in_tab = True

def style(node, rules, tab):
    old_style = node.style

    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value

    for media, selector, body in rules:
        if media:
            if (media == "dark") != tab.dark_mode: continue
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

    if old_style:
        transitions = diff_styles(old_style, node.style)
        for property, (old_value, new_value, num_frames) \
            in transitions.items():
            if property == "opacity":
                tab.set_needs_render()
                animation = NumericAnimation(
                    old_value, new_value, num_frames)
                node.animations[property] = animation
                node.style[property] = animation.animate()

    for child in node.children:
        style(child, rules, tab)

def parse_transition(value):
    properties = {}
    if not value: return properties
    for item in value.split(","):
        property, duration = item.split(" ", 1)
        frames = int(float(duration[:-1]) / REFRESH_RATE_SEC)
        properties[property] = frames
    return properties

def diff_styles(old_style, new_style):
    transitions = {}
    for property, num_frames in \
        parse_transition(new_style.get("transition")).items():
        if property not in old_style: continue
        if property not in new_style: continue
        old_value = old_style[property]
        new_value = new_style[property]
        if old_value == new_value: continue
        transitions[property] = \
            (old_value, new_value, num_frames)

    return transitions

def cascade_priority(rule):
    media, selector, body = rule
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