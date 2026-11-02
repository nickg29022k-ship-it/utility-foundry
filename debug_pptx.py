from pptx import Presentation
from pptx.oxml.ns import qn
from lxml import etree

prs = Presentation("WORKING VERSION.pptx")
slide = prs.slides[0]

# Print ALL shapes flat with their absolute positions and type
def walk(shapes, depth=0, off_x=0, off_y=0):
    for shape in shapes:
        left = (shape.left or 0) + off_x
        top  = (shape.top  or 0) + off_y
        w    = shape.width  or 0
        h    = shape.height or 0
        name = ""
        if shape.has_text_frame:
            name = repr(shape.text_frame.text.strip()[:40])
        blip = shape._element.find('.//' + qn('a:blip'))
        has_img = blip is not None
        print(f"{'  '*depth}[type={shape.shape_type}] {shape.name:25s} left={left:10d} top={top:10d} img={has_img} text={name}")
        if shape.shape_type == 6:
            walk(shape.shapes, depth+1, left, top)

walk(slide.shapes)
