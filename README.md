# Convert Inkscape figures to typst
A script to bridge Inkscape and Typst.

This script processes an SVG file from Inkscape to create a Typst-friendly
figure, separating graphics from text. It replicates the functionality of
LaTeX's 'PDF + LaTeX' export option for Typst documents.

It takes one argument: the path to an Inkscape SVG file.
e.g., 
```sh
python3 typst_inkscape.py my_diagram.svg
```

It produces two files:
1.  `my_diagram_clean.svg`: The original graphics with all text removed.
2.  `my_diagram.typ`: A Typst script that overlays the text, typeset by
    Typst, onto the cleaned SVG.

This allows figures to seamlessly inherit the main document's fonts and
math rendering quality.

How to use such figures:
```typst
#import "drawing.typ":diagram as myfig

#myfig() //the size will be set automatically
 
#myfig(width:360pt) // set your custom size
```

## Dependencies
- `python`
- lxml: For robust SVG parsing and manipulation.
- numpy: For accurate handling of SVG transformation matrices.

Install them with:
```sh
pip3 install lxml numpy
```

