from setting.constant import *

class ProtectedField:
    def __init__(self, obj, name, parent=None, dependencies=None, invalidations=None):
        self.obj = obj
        self.name = name
        self.parent = parent

        self.value = None
        self.dirty = True
        self.invalidations = set()
        self.frozen_dependencies = (dependencies != None)
        if dependencies != None:
            for dependency in dependencies:
                dependency.invalidations.add(self)
        else:
            assert \
                self.name in [
                    "height", "ascent", "descent", "children"
                ] or self.name in CSS_PROPERTIES

        self.frozen_invalidations = invalidations != None
        if invalidations != None:
            assert self.name == "children"
            for invalidation in invalidations:
                self.invalidations.add(invalidation)

    def set_dependencies(self, dependencies):
        assert self.name in ["height", "ascent", "descent"] or \
            self.name in CSS_PROPERTIES
        assert self.name == "height" or not self.frozen_dependencies
        for dependency in dependencies:
            dependency.invalidations.add(self)
        self.frozen_dependencies = True

    def set_ancestor_dirty_bits(self):
        parent = self.parent
        while parent and not parent.has_dirty_descendants:
            parent.has_dirty_descendants = True
            parent = parent.parent

    def mark(self):
        if self.dirty: return
        self.dirty = True
        self.set_ancestor_dirty_bits()

    def notify(self):
        for field in self.invalidations:
            field.mark()
        self.set_ancestor_dirty_bits()

    def set(self, value):
        # if self.value != None:
        #     print("Change", self)
        if value != self.value:
            self.notify()
        self.value = value
        self.dirty = False

    def get(self):
        assert not self.dirty
        return self.value

    def read(self, notify):
        if notify.frozen_dependencies or self.frozen_invalidations:
            assert notify in self.invalidations
        else:
            self.invalidations.add(notify)

        if False:
            prefix = ""
            if notify.obj == self.obj:
                prefix = "self."
            elif self.obj == notify.parent:
                prefix = "self.parent."
            elif notify.obj == self.obj.parent:
                prefix = "self.child."
            elif hasattr(notify.obj, "previous") and \
                notify.obj.previous == self.obj:
                    prefix = "self.previous."
            print("{} depends on {}{}".format(
                notify.name, prefix, self.name))

        return self.get()

    def copy(self, field):
        self.set(field.read(notify=self))

    def __str__(self):
        if self.dirty:
            return "<dirty>"
        else:
            return str(self.value)

    def __repr__(self):
        return "ProtectedField({}, {})".format(
            self.obj.node if hasattr(self.obj, "node") else self.obj,
            self.name)