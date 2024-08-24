from parser.css_parser import CSSParser

DEFAULT_STYLE_SHEET = CSSParser(open("setting/browser.css").read()).parse()

class Config:
    dark_mode = False