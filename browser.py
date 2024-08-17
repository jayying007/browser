import ctypes
import sdl2
import skia
import math
import OpenGL.GL
import os
import gtts
import playsound
from chrome import *
from tab import *
from network import *
from config import *
from util import *
from task import *
from measure import *

class Browser:
    def __init__(self):
        self.chrome = Chrome(self)

        self.tabs = []
        self.active_tab = None
        self.focus = None
        self.address_bar = ""
        self.lock = threading.Lock()
        self.active_tab_url = None
        self.active_tab_scroll = 0

        self.animation_timer = None

        self.needs_animation_frame = False
        self.needs_composite = False
        self.needs_raster = False
        self.needs_draw = False
        self.needs_accessibility = False

        self.active_tab_height = 0
        self.active_tab_display_list = None

        self.composited_updates = {}
        self.composited_layers = []
        self.draw_list = []
        self.muted = True
        self.dark_mode = False

        self.accessibility_is_on = False
        self.has_spoken_document = False
        self.pending_hover = None
        self.hovered_a11y_node = None
        self.focus_a11y_node = None
        self.needs_speak_hovered_node = False
        self.tab_focus = None
        self.last_tab_focus = None
        self.active_alerts = []
        self.spoken_alerts = []
        self.root_frame_focused = False

        self.measure = MeasureTime()
        threading.current_thread().name = "Browser thread"

        if sdl2.SDL_BYTEORDER == sdl2.SDL_BIG_ENDIAN:
            self.RED_MASK = 0xff000000
            self.GREEN_MASK = 0x00ff0000
            self.BLUE_MASK = 0x0000ff00
            self.ALPHA_MASK = 0x000000ff
        else:
            self.RED_MASK = 0x000000ff
            self.GREEN_MASK = 0x0000ff00
            self.BLUE_MASK = 0x00ff0000
            self.ALPHA_MASK = 0xff000000

        self.sdl_window = sdl2.SDL_CreateWindow(b"Browser",
                sdl2.SDL_WINDOWPOS_CENTERED,
                sdl2.SDL_WINDOWPOS_CENTERED,
                WIDTH, HEIGHT,
                sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_OPENGL)

        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 3)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 2)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_PROFILE_MASK,
                                    sdl2.SDL_GL_CONTEXT_PROFILE_CORE)

        self.gl_context = sdl2.SDL_GL_CreateContext(
            self.sdl_window)
        print(("OpenGL initialized: vendor={}," + \
            "renderer={}").format(
            OpenGL.GL.glGetString(OpenGL.GL.GL_VENDOR),
            OpenGL.GL.glGetString(OpenGL.GL.GL_RENDERER)))

        self.skia_context = skia.GrDirectContext.MakeGL()

        self.root_surface = \
            skia.Surface.MakeFromBackendRenderTarget(
            self.skia_context,
            skia.GrBackendRenderTarget(
                WIDTH, HEIGHT, 0, 0, 
                skia.GrGLFramebufferInfo(0, OpenGL.GL.GL_RGBA8)),
                skia.kBottomLeft_GrSurfaceOrigin,
                skia.kRGBA_8888_ColorType,
                skia.ColorSpace.MakeSRGB())
        assert self.root_surface is not None

        self.chrome_surface = skia.Surface.MakeRenderTarget(
                self.skia_context, skia.Budgeted.kNo,
                skia.ImageInfo.MakeN32Premul(WIDTH, math.ceil(self.chrome.bottom)))
        assert self.chrome_surface is not None
    # 创建一个新Tab
    def new_tab(self, url):
        self.lock.acquire(blocking=True)
        self.new_tab_internal(url)
        self.lock.release()

    def new_tab_internal(self, url):
        new_tab = Tab(self, HEIGHT - self.chrome.bottom)
        self.tabs.append(new_tab)
        self.set_active_tab(new_tab)
        self.schedule_load(url)

    # 当前Tab加载一个网址
    def schedule_load(self, url, body=None):
        self.active_tab.task_runner.clear_pending_tasks()
        task = Task(self.active_tab.load, url, body)
        self.active_tab.task_runner.schedule_task(task)

    def set_active_tab(self, tab):
        self.active_tab = tab
        task = Task(self.active_tab.set_dark_mode, self.dark_mode)
        self.active_tab.task_runner.schedule_task(task)
        task = Task(self.active_tab.set_needs_render_all_frames)
        self.active_tab.task_runner.schedule_task(task)

        self.clear_data()
        self.needs_animation_frame = True
        self.animation_timer = None

    def clear_data(self):
        self.active_tab_scroll = 0
        self.active_tab_url = None
        self.display_list = []
        self.composited_layers = []
        self.composited_updates = {}
        self.accessibility_tree = None

    ##########################
    # 渲染
    ##########################
    def set_needs_draw(self):
        self.needs_draw = True
    
    def set_needs_raster(self):
        self.needs_raster = True
        self.needs_draw = True

    def set_needs_composite(self):
        self.needs_composite = True
        self.needs_raster = True
        self.needs_draw = True

    def composite_raster_and_draw(self):
        self.lock.acquire(blocking=True)
        if not self.needs_composite and \
            len(self.composited_updates) == 0 \
            and not self.needs_raster and not self.needs_draw and not \
            self.needs_accessibility:
            self.lock.release()
            return

        self.measure.time('composite_raster_and_draw')
        if self.needs_composite:
            self.measure.time('composite')
            self.composite()
            self.measure.stop('composite')
        if self.needs_raster:
            self.measure.time('raster')
            self.raster_chrome()
            self.raster_tab()
            self.measure.stop('raster')
        if self.needs_draw:
            self.measure.time('draw')
            self.paint_draw_list()
            self.draw()
            self.measure.stop('draw')
        self.measure.stop('composite_raster_and_draw')

        if self.needs_accessibility:
            self.update_accessibility()

        self.needs_composite = False
        self.needs_raster = False
        self.needs_draw = False
        self.needs_accessibility = False
        self.lock.release()

    def composite(self):
        self.composited_layers = []
        add_parent_pointers(self.active_tab_display_list)
        
        all_commands = []
        for cmd in self.active_tab_display_list:
            all_commands = tree_to_list(cmd, all_commands)

        non_composited_commands = [cmd
            for cmd in all_commands
            if isinstance(cmd, PaintCommand) or \
                not cmd.needs_compositing
            if not cmd.parent or cmd.parent.needs_compositing
        ]
        for cmd in non_composited_commands:
            did_break = False
            for layer in reversed(self.composited_layers):
                if layer.can_merge(cmd):
                    layer.add(cmd)
                    did_break = True
                    break
                elif skia.Rect.Intersects(
                    layer.absolute_bounds(),
                    local_to_absolute(cmd, cmd.rect)):
                    layer = CompositedLayer(self.skia_context, cmd)
                    self.composited_layers.append(layer)
                    did_break = True
                    break
            if not did_break:
                layer = CompositedLayer(self.skia_context, cmd)
                self.composited_layers.append(layer)

        self.active_tab_height = 0
        for layer in self.composited_layers:
            self.active_tab_height = \
                max(self.active_tab_height,
                    layer.absolute_bounds().bottom())

    def raster_chrome(self):
        canvas = self.chrome_surface.getCanvas()
        if self.dark_mode:
            background_color = skia.ColorBLACK
        else:
            background_color = skia.ColorWHITE
        canvas.clear(background_color)

        for cmd in self.chrome.paint():
            cmd.execute(canvas)

    def raster_tab(self):
        for composited_layer in self.composited_layers:
            composited_layer.raster()

    def paint_draw_list(self):
        new_effects = {}
        self.draw_list = []
        for composited_layer in self.composited_layers:
            current_effect = \
                DrawCompositedLayer(composited_layer)
            if not composited_layer.display_items: continue
            parent = composited_layer.display_items[0].parent
            while parent:
                new_parent = self.get_latest(parent)
                if new_parent in new_effects:
                    new_effects[new_parent].children.append(
                        current_effect)
                    break
                else:
                    current_effect = \
                        new_parent.clone(current_effect)
                    new_effects[new_parent] = current_effect
                    parent = parent.parent
            if not parent:
                self.draw_list.append(current_effect)

        if self.pending_hover:
            (x, y) = self.pending_hover
            y += self.active_tab_scroll
            a11y_node = self.accessibility_tree.hit_test(x, y)
            if a11y_node:
                if not self.hovered_a11y_node or \
                    a11y_node.node != self.hovered_a11y_node.node:
                    self.needs_speak_hovered_node = True
                self.hovered_a11y_node = a11y_node
        self.pending_hover = None

        if self.hovered_a11y_node:
            for bound in self.hovered_a11y_node.bounds:
                self.draw_list.append(DrawOutline(
                    bound,
                    "white" if self.dark_mode else "black", 2))

    def get_latest(self, effect):
        node = effect.node
        if node not in self.composited_updates:
            return effect
        if not isinstance(effect, Blend):
            return effect
        return self.composited_updates[node]

    def draw(self):
        canvas = self.root_surface.getCanvas()
        if self.dark_mode:
            canvas.clear(skia.ColorBLACK)
        else:
            canvas.clear(skia.ColorWHITE)

        canvas.save()
        canvas.translate(0, self.chrome.bottom - self.active_tab_scroll)
        for item in self.draw_list:
            item.execute(canvas)
        canvas.restore()

        chrome_rect = skia.Rect.MakeLTRB(0, 0, WIDTH, self.chrome.bottom)
        canvas.save()
        canvas.clipRect(chrome_rect)
        self.chrome_surface.draw(canvas, 0, 0)
        canvas.restore()

        self.root_surface.flushAndSubmit()
        sdl2.SDL_GL_SwapWindow(self.sdl_window)

    # 动画
    def set_needs_animation_frame(self, tab):
        self.lock.acquire(blocking=True)
        if tab == self.active_tab:
            self.needs_animation_frame = True
        self.lock.release()

    def schedule_animation_frame(self):
        def callback():
            self.lock.acquire(blocking=True)
            scroll = self.active_tab_scroll
            active_tab = self.active_tab
            self.needs_animation_frame = False
            self.lock.release()
            task = Task(self.active_tab.run_animation_frame, scroll)
            active_tab.task_runner.schedule_task(task)
        self.lock.acquire(blocking=True)
        if self.needs_animation_frame and not self.animation_timer:
            self.animation_timer = threading.Timer(REFRESH_RATE_SEC, callback)
            self.animation_timer.start()
        self.lock.release()

    def commit(self, tab, data):
        self.lock.acquire(blocking=True)
        if tab == self.active_tab:
            self.active_tab_url = data.url
            if data.scroll != None:
                self.active_tab_scroll = data.scroll
            self.root_frame_focused = data.root_frame_focused
            self.active_tab_height = data.height
            if data.display_list:
                self.active_tab_display_list = data.display_list
            self.animation_timer = None
            self.composited_updates = data.composited_updates
            self.accessibility_tree = data.accessibility_tree
            if self.accessibility_tree:
                self.set_needs_accessibility()
            if self.composited_updates == None:
                self.composited_updates = {}
                self.set_needs_composite()
            else:
                self.set_needs_draw()
        self.lock.release()

    ##############################
    # 用户事件
    ##############################
    def handle_quit(self):
        self.measure.finish()
        for tab in self.tabs:
            tab.task_runner.set_needs_quit()
        sdl2.SDL_GL_DeleteContext(self.gl_context)
        sdl2.SDL_DestroyWindow(self.sdl_window)

    def handle_click(self, e):
        self.lock.acquire(blocking=True)
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
            self.set_needs_raster()
        else:
            if self.focus != "content":
                self.set_needs_raster()
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            task = Task(self.active_tab.click, e.x, tab_y)
            self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def handle_key(self, char):
        self.lock.acquire(blocking=True)
        if not (0x20 <= ord(char) < 0x7f): return
        if self.chrome.keypress(char):
            self.set_needs_raster()
        elif self.focus == "content":
            task = Task(self.active_tab.keypress, char)
            self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def handle_enter(self):
        self.lock.acquire(blocking=True)
        if self.chrome.enter():
            self.set_needs_raster()
        elif self.focus == "content":
            task = Task(self.active_tab.enter)
            self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def clamp_scroll(self, scroll):
        height = self.active_tab_height
        maxscroll = height - (HEIGHT - self.chrome.bottom)
        return max(0, min(scroll, maxscroll))

    def handle_down(self):
        self.lock.acquire(blocking=True)
        if self.root_frame_focused:
            if not self.active_tab_height:
                self.lock.release()
                return
            self.active_tab_scroll = \
                self.clamp_scroll(self.active_tab_scroll + SCROLL_STEP)
            self.set_needs_draw()
            self.needs_animation_frame = True
            self.lock.release()
            return
        task = Task(self.active_tab.scrolldown)
        self.active_tab.task_runner.schedule_task(task)
        self.needs_animation_frame = True
        self.lock.release()

    def increment_zoom(self, increment):
        task = Task(self.active_tab.zoom_by, increment)
        self.active_tab.task_runner.schedule_task(task)

    def reset_zoom(self):
        task = Task(self.active_tab.reset_zoom)
        self.active_tab.task_runner.schedule_task(task)

    def toggle_dark_mode(self):
        self.lock.acquire(blocking=True)
        self.dark_mode = not self.dark_mode
        task = Task(self.active_tab.set_dark_mode, self.dark_mode)
        self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def go_back(self):
        task = Task(self.active_tab.go_back)
        self.active_tab.task_runner.schedule_task(task)
        self.clear_data()

    def focus_addressbar(self):
        self.lock.acquire(blocking=True)
        self.focus = None
        self.chrome.focus_addressbar()
        text = "Address bar focused"
        if self.accessibility_is_on:
            speak_text(text)
        self.set_needs_raster()
        self.lock.release()

    def focus_content(self):
        self.lock.acquire(blocking=True)
        self.chrome.blur()
        self.focus = "content"
        self.lock.release()

    def cycle_tabs(self):
        self.lock.acquire(blocking=True)
        active_idx = self.tabs.index(self.active_tab)
        new_active_idx = (active_idx + 1) % len(self.tabs)
        self.set_active_tab(self.tabs[new_active_idx])
        self.lock.release()

    def handle_tab(self):
        self.focus = "content"
        task = Task(self.active_tab.advance_tab)
        self.active_tab.task_runner.schedule_task(task)

    def toggle_accessibility(self):
        self.lock.acquire(blocking=True)
        self.accessibility_is_on = not self.accessibility_is_on
        self.set_needs_accessibility()
        self.lock.release()

    def set_needs_accessibility(self):
        if not self.accessibility_is_on:
            return
        self.needs_accessibility = True
        self.needs_draw = True

        self.active_tab_height = 0
        for layer in self.composited_layers:
            self.active_tab_height = \
                max(self.active_tab_height,
                    layer.absolute_bounds().bottom())

    def update_accessibility(self):
        if not self.accessibility_tree: return

        if not self.has_spoken_document:
            self.speak_document()
            self.has_spoken_document = True

        self.active_alerts = [
            node for node in tree_to_list(
                self.accessibility_tree, [])
            if node.role == "alert"
        ]

        for alert in self.active_alerts:
            if alert not in self.spoken_alerts:
                self.speak_node(alert, "New alert")
                self.spoken_alerts.append(alert)

        new_spoken_alerts = []
        for old_node in self.spoken_alerts:
            new_nodes = [
                node for node in tree_to_list(
                    self.accessibility_tree, [])
                if node.node == old_node.node
                and node.role == "alert"
            ]
            if new_nodes:
                new_spoken_alerts.append(new_nodes[0])
        self.spoken_alerts = new_spoken_alerts

        if self.tab_focus and \
            self.tab_focus != self.last_tab_focus:
            nodes = [node for node in tree_to_list(
                self.accessibility_tree, [])
                        if node.node == self.tab_focus]
            if nodes:
                self.focus_a11y_node = nodes[0]
                self.speak_node(
                    self.focus_a11y_node, "element focused ")
            self.last_tab_focus = self.tab_focus

        if self.needs_speak_hovered_node:
            self.speak_node(self.hovered_a11y_node, "Hit test ")
        self.needs_speak_hovered_node = False

    def speak_document(self):
        text = "Here are the document contents: "
        tree_list = tree_to_list(self.accessibility_tree, [])
        for accessibility_node in tree_list:
            new_text = accessibility_node.text
            if new_text:
                text += "\n"  + new_text

        speak_text(text)

    def speak_node(self, node, text):
        text += node.text
        if text and node.children and \
            node.children[0].role == "StaticText":
            text += " " + \
            node.children[0].text

        speak_text(text)

    def handle_hover(self, event):
        if not self.accessibility_is_on or not self.accessibility_tree:
            return
        self.pending_hover = (event.x, event.y - self.chrome.bottom)
        self.set_needs_accessibility()

def mainloop(browser: Browser):
    event = sdl2.SDL_Event()
    ctrl_down = False
    while True:
        if sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == sdl2.SDL_QUIT:
                browser.handle_quit()
                sdl2.SDL_Quit()
                sys.exit()
            elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                browser.handle_click(event.button)
            elif event.type == sdl2.SDL_MOUSEMOTION:
                browser.handle_hover(event.motion)
            elif event.type == sdl2.SDL_KEYDOWN:
                if ctrl_down:
                    if event.key.keysym.sym == sdl2.SDLK_EQUALS:
                        browser.increment_zoom(True)
                    elif event.key.keysym.sym == sdl2.SDLK_MINUS:
                        browser.increment_zoom(False)
                    elif event.key.keysym.sym == sdl2.SDLK_0:
                        browser.reset_zoom()
                    elif event.key.keysym.sym == sdl2.SDLK_LEFT:
                        browser.go_back()
                    elif event.key.keysym.sym == sdl2.SDLK_l:
                        browser.focus_addressbar()
                    elif event.key.keysym.sym == sdl2.SDLK_a:
                        browser.toggle_accessibility()
                    elif event.key.keysym.sym == sdl2.SDLK_d:
                        browser.toggle_dark_mode()
                    elif event.key.keysym.sym == sdl2.SDLK_t:
                        browser.new_tab( "https://browser.engineering/")
                    elif event.key.keysym.sym == sdl2.SDLK_TAB:
                        browser.cycle_tabs()
                    elif event.key.keysym.sym == sdl2.SDLK_q:
                        browser.handle_quit()
                        sdl2.SDL_Quit()
                        sys.exit()
                elif event.key.keysym.sym == sdl2.SDLK_RETURN:
                    browser.handle_enter()
                elif event.key.keysym.sym == sdl2.SDLK_DOWN:
                    browser.handle_down()
                elif event.key.keysym.sym == sdl2.SDLK_TAB:
                    browser.handle_tab()
                elif event.key.keysym.sym == sdl2.SDLK_RCTRL or \
                    event.key.keysym.sym == sdl2.SDLK_LCTRL:
                    ctrl_down = True
            elif event.type == sdl2.SDL_KEYUP:
                if event.key.keysym.sym == sdl2.SDLK_RCTRL or \
                    event.key.keysym.sym == sdl2.SDLK_LCTRL:
                    ctrl_down = False
            elif event.type == sdl2.SDL_TEXTINPUT and not ctrl_down:
                browser.handle_key(event.text.text.decode('utf8'))
        browser.composite_raster_and_draw()
        browser.schedule_animation_frame()

SPEECH_FILE = "/tmp/speech-fragment.mp3"
def speak_text(text):
    print("SPEAK:", text)
    # tts = gtts.gTTS(text)
    # tts.save(SPEECH_FILE)
    # playsound.playsound(SPEECH_FILE)
    # os.remove(SPEECH_FILE)

if __name__ == "__main__":
    import sys
    sdl2.SDL_Init(sdl2.SDL_INIT_EVENTS)
    browser = Browser()
    browser.new_tab(URL(sys.argv[1]))
    browser.draw()
    mainloop(browser)