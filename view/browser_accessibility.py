from view.accessibility import *

class BrowserAccessibility:
    def __init__(self, browser, accessibility_tree):
        self.browser = browser
        self.accessibility_tree: AccessibilityNode = accessibility_tree

        self.has_spoken_document = False
        self.needs_speak_hovered_node = False

        self.active_alerts = []
        self.spoken_alerts = []

    def handle_hover(self, x, y):
        a11y_node = self.accessibility_tree.hit_test(x, y)
        if a11y_node:
            if not self.browser.hovered_a11y_node or a11y_node.node != self.browser.hovered_a11y_node.node:
                self.needs_speak_hovered_node = True
        return a11y_node

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

        if self.browser.tab_focus and self.browser.tab_focus != self.browser.last_tab_focus:
            nodes = [node for node in tree_to_list(
                self.accessibility_tree, [])
                        if node.node == self.browser.tab_focus]
            if nodes:
                self.focus_a11y_node = nodes[0]
                self.speak_node(self.focus_a11y_node, "element focused ")
            self.browser.last_tab_focus = self.browser.tab_focus

        if self.needs_speak_hovered_node:
            self.speak_node(self.browser.hovered_a11y_node, "Hit test ")
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