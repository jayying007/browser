from common.protected_field import *
from parser.css_parser import *
from layout.iframe_layout import *
from display.animation import *
from setting.config import *
from display.paint_command import *
from display.visual_effect import *

def dirty_style(node):
    if not node.style:
        return
    for property, value in node.style.items():
        value.mark()

def init_style(node):
    node.style = dict([
            (property, ProtectedField(node, property, None,
                [node.parent.style[property]] if node.parent and property in INHERITED_PROPERTIES else []))
            for property in CSS_PROPERTIES
        ])

def style(node, rules, frame):
    if not node.style:
        init_style(node)
    needs_style = any([field.dirty for field in node.style.values()])

    if needs_style:
        old_style = dict([
            (property, field.value)
            for property, field in node.style.items()
        ])
        new_style = CSS_PROPERTIES.copy()
        for property, default_value in INHERITED_PROPERTIES.items():
            if node.parent:
                parent_field = node.parent.style[property]
                parent_value = parent_field.read(notify=node.style[property])
                new_style[property] = parent_value
            else:
                new_style[property] = default_value
        for media, selector, body in rules:
            if media:
                if (media == 'dark') != Config.dark_mode: continue
            if not selector.matches(node): continue
            for property, value in body.items():
                new_style[property] = value
        if isinstance(node, Element) and 'style' in node.attributes:
            pairs = CSSParser(node.attributes['style']).body()
            for property, value in pairs.items():
                new_style[property] = value
        if new_style["font-size"].endswith("%"):
            if node.parent:
                parent_field = node.parent.style["font-size"]
                parent_font_size = \
                    parent_field.read(notify=node.style["font-size"])
            else:
                parent_font_size = INHERITED_PROPERTIES["font-size"]
            node_pct = float(new_style["font-size"][:-1]) / 100
            parent_px = float(parent_font_size[:-2])
            new_style["font-size"] = str(node_pct * parent_px) + "px"
        if old_style:
            transitions = diff_styles(old_style, new_style)
            for property, (old_value, new_value, num_frames) in \
                transitions.items():
                if property == "opacity":
                    frame.set_needs_render()
                    animation = NumericAnimation(old_value, new_value, num_frames)
                    node.animations[property] = animation
                    new_style[property] = animation.animate()
        for property, field in node.style.items():
            field.set(new_style[property])

    for child in node.children:
        style(child, rules, frame)

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

def parse_transition(value):
    properties = {}
    if not value: return properties
    for item in value.split(","):
        property, duration = item.split(" ", 1)
        frames = int(float(duration[:-1]) / REFRESH_RATE_SEC)
        properties[property] = frames
    return properties

def paint_visual_effects(node, cmds, rect):
    opacity = float(node.style["opacity"].get())
    blend_mode = node.style["mix-blend-mode"].get()
    translation = parse_transform(node.style["transform"].get())

    if node.style["overflow"].get() == "clip":
        border_radius = float(node.style["border-radius"].get()[:-2])
        if not blend_mode:
            blend_mode = "source-over"
        cmds = [Blend(1.0, "source-over", node,
                      cmds + [Blend(1.0, "destination-in", None, [DrawRRect(rect, 0, "white")])])]

    blend_op = Blend(opacity, blend_mode, node, cmds)
    node.blend_op = blend_op
    return [Transform(translation, rect, node, [blend_op])]

def paint_outline(node, cmds, rect, zoom):
    outline = parse_outline(node.style["outline"].get())
    if not outline: return
    thickness, color = outline
    cmds.append(DrawOutline(rect, color, dpx(thickness, zoom)))

def parse_outline(outline_str):
    if not outline_str: return None
    values = outline_str.split(" ")
    if len(values) != 3: return None
    if values[1] != "solid": return None
    return int(values[0][:-2]), values[2]