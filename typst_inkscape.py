#!/usr/bin/env python

"""
A script to bridge Inkscape and Typst.

This script processes an SVG file from Inkscape to create a Typst-friendly
figure, separating graphics from text. It replicates the functionality of
LaTeX's 'PDF + LaTeX' export option for Typst documents.

It takes one argument: the path to an Inkscape SVG file.
e.g., python typst_inkscape.py my_diagram.svg

It produces two files:
1.  my_diagram_clean.svg: The original graphics with all text removed.
2.  my_diagram.typ: A Typst script that overlays the text, typeset by
    Typst, onto the cleaned SVG.

This allows figures to seamlessly inherit the main document's fonts and
math rendering quality.

Dependencies:
- lxml: For robust SVG parsing and manipulation.
- numpy: For accurate handling of SVG transformation matrices.

Install them with:
pip3 install lxml numpy
"""

import sys
import os
import re
import lxml.etree as etree
import numpy as np

PX_TO_PT = 72.0 / 96.0  
SVG_NS = "http://www.w3.org/2000/svg"
NAMESPACES = {'svg': SVG_NS}


def parse_svg_dimensions(root):
    """
    Extracts the width and height of the SVG in points.
    Prioritizes width/height attributes, falls back to viewBox.
    """
    width_str = root.get('width')
    height_str = root.get('height')

    if width_str and height_str:
        w = float(re.sub(r'[^\d.]', '', width_str))
        h = float(re.sub(r'[^\d.]', '', height_str))
        # Assume px if no units are specified, which is standard
        return w * PX_TO_PT, h * PX_TO_PT
    
    if 'viewBox' in root.attrib:
        _, _, w_vb, h_vb = map(float, root.attrib['viewBox'].split())
        # If no width/height, 1 user unit in viewBox = 1px
        return w_vb * PX_TO_PT, h_vb * PX_TO_PT
    
    raise ValueError("SVG has no width/height or viewBox attribute.")

def parse_transform(transform_str):
    """
    Parses an SVG transform string into a 3x3 NumPy matrix.
    Supports matrix, translate, and scale.
    """
    if not transform_str:
        return np.identity(3)

    total_transform = np.identity(3)
    
    # Regex to find all transform functions
    pattern = r'\s*(matrix|translate|scale)\s*\(([^)]+)\)'
    matches = re.findall(pattern, transform_str)

    for func, args_str in matches:
        args = [float(arg) for arg in re.split(r'[,\s]+', args_str.strip())]
        m = np.identity(3)
        if func == 'matrix' and len(args) == 6:
            a, b, c, d, e, f = args
            m[0, 0] = a; m[0, 1] = c; m[0, 2] = e
            m[1, 0] = b; m[1, 1] = d; m[1, 2] = f
        elif func == 'translate':
            tx = args[0]
            ty = args[1] if len(args) > 1 else 0
            m[0, 2] = tx
            m[1, 2] = ty
        elif func == 'scale':
            sx = args[0]
            sy = args[1] if len(args) > 1 else sx
            m[0, 0] = sx
            m[1, 1] = sy
        
        total_transform = m @ total_transform
        
    return total_transform

def get_cumulative_transform(element):
    """
    Accumulates transformations from an element up to the SVG root.
    """
    transform = np.identity(3)
    # The `iterancestors` method comes from lxml's element objects
    for ancestor in element.iterancestors():
        # Stop at the root <svg> element
        if ancestor.tag == etree.QName(SVG_NS, 'svg'):
            break
        transform_str = ancestor.get('transform', '')
        ancestor_transform = parse_transform(transform_str)
        transform = ancestor_transform @ transform
        
    # Also include the element's own transform
    element_transform_str = element.get('transform', '')
    element_transform = parse_transform(element_transform_str)
    transform = transform @ element_transform

    return transform

def process_svg(input_path):
    """
    Main function to process the SVG file.
    """
    # Parse SVG and Prepare
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(input_path, parser)
        root = tree.getroot()
    except Exception as e:
        print(f"Error: Could not parse SVG file '{input_path}'.\n{e}")
        sys.exit(1)

    # Extract Dimensions
    try:
        width_pt, height_pt = parse_svg_dimensions(root)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    print(f"Detected figure dimensions: {width_pt:.2f}pt x {height_pt:.2f}pt")

    # Find and Process Text Elements
    labels = []
    text_nodes_to_remove = []
    
    # Find all <text> elements 
    for text_node in root.xpath('//svg:text', namespaces=NAMESPACES):
        # Extract Raw Attributes 
        x = float(text_node.get('x', '0'))
        y = float(text_node.get('y', '0'))
        
        # Font size from style attribute 
        style = text_node.get('style', '')
        font_size_match = re.search(r'font-size:([\d.]+)px', style)
        font_size_px = float(font_size_match.group(1)) if font_size_match else 16.0 # Default

        # Text anchor from style or attribute
        anchor_match = re.search(r'text-anchor:(start|middle|end)', style)
        text_anchor = anchor_match.group(1) if anchor_match else text_node.get('text-anchor', 'start')
        
        # Get Text Content (handles <tspan>) 
        raw_text = "".join(text_node.itertext()).strip()
        if not raw_text:
            continue

        # Accumulate Transforms
        transform_matrix = get_cumulative_transform(text_node)
        
        # Apply matrix to the text's (x,y) coordinates
        transformed_point = transform_matrix @ np.array([x, y, 1])
        final_x_px, final_y_px = transformed_point[0], transformed_point[1]

        # Apply Transforms to Font Size
        sy = np.sqrt(transform_matrix[1, 0]**2 + transform_matrix[1, 1]**2)
        final_font_size_px = font_size_px * sy
        
        # Unit Conversion and Baseline Adjustment 
        final_x_pt = final_x_px * PX_TO_PT
        final_y_pt = final_y_px * PX_TO_PT
        final_font_size_pt = final_font_size_px * PX_TO_PT
        ascent_estimate = 0.8 * final_font_size_pt
        final_y_pt -= ascent_estimate

        content = raw_text
        
        # Store Processed Label Info 
        labels.append({
            'x_pt': final_x_pt,
            'y_pt': final_y_pt,
            'font_size_pt': final_font_size_pt,
            'content': content,
            'anchor': text_anchor
        })
        
        # Mark node for removal
        text_nodes_to_remove.append(text_node)

    # Clean the SVG 
    for node in text_nodes_to_remove:
        node.getparent().remove(node)
        
    base, _ = os.path.splitext(input_path)
    clean_svg_path = f"{base}_clean.svg"
    # The lxml tree object handles writing perfectly.
    tree.write(clean_svg_path, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    print(f"Successfully created clean SVG: '{clean_svg_path}'")

    # Generate the Typst File 
    typst_path = f"{base}.typ"
    clean_svg_filename = os.path.basename(clean_svg_path)
    
    # Header and scaling logic
    typst_code = [
        f'// Auto-generated by typst_inkscape.py from {os.path.basename(input_path)}',
        f'#let diagram(width: auto) = {{',
        f'  // Original dimensions: {width_pt:.2f}pt x {height_pt:.2f}pt',
        f'  let W = {width_pt:.4f}pt',
        f'  let H = {height_pt:.4f}pt',
        f'  let s = if width == auto {{ 1.0 }} else {{ width / W }}',
        f'',
        f'  stack(',
    ]

    # Add each label
    for label in labels:
        content_escaped = label['content'].replace('\\', '\\\\').replace('"', '\\"')
        typst_text = f'{content_escaped}'
        
        align_map = {'start': 'left', 'middle': 'center', 'end': 'right'}
        typst_align = align_map.get(label['anchor'], 'left')

        move_call = (
            f'    place('
            f'dx: s * {label["x_pt"]:.4f}pt, dy: s * {label["y_pt"]:.4f}pt, '
            f'align(horizon + {typst_align})['
            f'  #block(text(size: s * {label["font_size_pt"]:.4f}pt)[{typst_text}])'
            f']),'
        )
        typst_code.append(move_call)

    typst_code.append(
        f'    image("{clean_svg_filename}", width: s * W),',
        )
    typst_code.append('  )')
    typst_code.append('}')

    with open(typst_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(typst_code))
    
    print(f"Successfully created Typst file: '{typst_path}'")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 typst_inkscape.py <path_to_your_svg_file.svg>")
        sys.exit(1)
        
    input_file = sys.argv[1]
    if not input_file.lower().endswith('.svg'):
        print(f"Error: Input file '{input_file}' is not an SVG file.")
        sys.exit(1)
        
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)

    process_svg(input_file)
    print(f"\nAll done! The {input_file} has been processed successfully!")


