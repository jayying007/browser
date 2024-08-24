import skia
from utils.util import *

def DrawCursor(elt, offset):
    x = elt.x.get() + offset
    return DrawLine(x, elt.y.get(), x, elt.y.get() + elt.height.get(), "red", 1)

class PaintCommand:
    def __init__(self, rect):
        self.rect = rect
        self.children = []

class DrawRect(PaintCommand):
    def __init__(self, rect, color):
        super().__init__(rect)
        self.rect = rect
        self.color = color

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
        )
        canvas.drawRect(self.rect, paint)

    def __repr__(self):
        return ("DrawRect(top={} left={} " +
            "bottom={} right={} color={})").format(
            self.top, self.left, self.bottom,
            self.right, self.color)

class DrawRRect(PaintCommand):
    def __init__(self, rect, radius, color):
        super().__init__(rect)
        self.rrect = skia.RRect.MakeRectXY(rect, radius, radius)
        self.color = color

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
        )
        canvas.drawRRect(self.rrect, paint)

    def __repr__(self):
        return "DrawRRect(rect={}, color={})".format(
            str(self.rrect), self.color)

class DrawText(PaintCommand):
    def __init__(self, x1, y1, text, font, color):
        self.left = x1
        self.top = y1
        self.right = x1 + font.measureText(text)
        self.bottom = y1 - font.getMetrics().fAscent + font.getMetrics().fDescent
        self.font = font
        self.text = text
        self.color = color
        super().__init__(skia.Rect.MakeLTRB(x1, y1,
            self.right, self.bottom))

    def execute(self, canvas):
        paint = skia.Paint(
            AntiAlias=True,
            Color=parse_color(self.color),
        )
        baseline = self.top - self.font.getMetrics().fAscent
        canvas.drawString(self.text, float(self.left), baseline,
            self.font, paint)

    def __repr__(self):
        return "DrawText(text={})".format(self.text)
    
class DrawOutline(PaintCommand):
    def __init__(self, rect, color, thickness):
        super().__init__(rect)
        self.color = color
        self.thickness = thickness

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawRect(self.rect, paint)

    def __repr__(self):
        return ("DrawOutline(top={} left={} " +
            "bottom={} right={} border_color={} " +
            "thickness={})").format(
            self.rect.top(), self.rect.left(), self.rect.bottom(),
            self.rect.right(), self.color,
            self.thickness)

class DrawLine(PaintCommand):
    def __init__(self, x1, y1, x2, y2, color, thickness):
        super().__init__(skia.Rect.MakeLTRB(x1, y1, x2, y2))
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.thickness = thickness

    def execute(self, canvas):
        path = skia.Path().moveTo(self.x1, self.y1) \
                          .lineTo(self.x2, self.y2)
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawPath(path, paint)

    def __repr__(self):
        return "DrawLine top={} left={} bottom={} right={}".format(
            self.y1, self.x1, self.y2, self.x2)
    
class DrawImage(PaintCommand):
    def __init__(self, image, rect, quality):
        super().__init__(rect)
        self.image = image
        self.quality = parse_image_rendering(quality)

    def execute(self, canvas):
        if int(skia.__version__.split(".")[0]) > 87:
            canvas.drawImageRect(self.image, self.rect, self.quality)
            return

        paint = skia.Paint(
            FilterQuality=self.quality,
        )
        canvas.drawImageRect(self.image, self.rect, paint)

    def __repr__(self):
        return "DrawImage(rect={})".format(
            self.rect)
    
class DrawCompositedLayer(PaintCommand):
    def __init__(self, composited_layer):
        self.composited_layer = composited_layer
        super().__init__(
            self.composited_layer.composited_bounds())

    def execute(self, canvas):
        layer = self.composited_layer
        if not layer.surface: return
        bounds = layer.composited_bounds()
        layer.surface.draw(canvas, bounds.left(), bounds.top())

    def __repr__(self):
        return "DrawCompositedLayer()"