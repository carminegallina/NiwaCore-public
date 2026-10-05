"""SELPHY P test sheet for measuring where the card falls on the borderless page.

    python selphy_calibration.py landscape NIWA-prova-SELPHY-P.jpg
    python selphy_calibration.py portrait NIWA-prova-SELPHY-P-verticale.jpg

Print it from the Canon app exactly as at an event (borderless, no crop or zoom).
On the short sides read the line that falls on the perforation; on the long sides
the first number left on the paper. Those millimetres go into SELPHY_PAGES in
app/app.py.
"""
import sys

from PIL import Image, ImageDraw, ImageFont

MM = 300 / 25.4
COLORS = [(0, 0, 0), (220, 30, 30), (20, 90, 220)]


def sheet(orientation):
    width, height = (1872, 1248) if orientation == "landscape" else (1248, 1872)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=20)
    text = ImageFont.load_default(size=26)

    def label(xy, value, fill, font=small):
        box = draw.textbbox(xy, value, font=font, anchor="mm")
        draw.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill="white")
        draw.text(xy, value, font=font, fill=fill, anchor="mm")

    # The perforations cross the long side of the paper, i.e. the page's short sides.
    vertical_reach = 16 if orientation == "landscape" else 10
    horizontal_reach = 10 if orientation == "landscape" else 16
    for mm in range(vertical_reach + 1):
        color = COLORS[mm % 3]
        for x in (round(mm * MM), width - 1 - round(mm * MM)):
            draw.line((x, 0, x, height), fill=color, width=3 if mm % 5 == 0 else 1)
            for y in (height * 0.2, height * 0.5, height * 0.8):
                label((x, y + (mm % 2) * 34), str(mm), color)
    for mm in range(horizontal_reach + 1):
        color = COLORS[mm % 3]
        for y in (round(mm * MM), height - 1 - round(mm * MM)):
            draw.line((0, y, width, y), fill=color, width=3 if mm % 5 == 0 else 1)
            for x in (width * 0.35, width * 0.5, width * 0.65):
                label((x + (mm % 2) * 40, y), str(mm), color)

    cx, cy = width // 2, height // 2
    draw.line((cx - 60, cy, cx + 60, cy), fill="black", width=3)
    draw.line((cx, cy - 60, cx, cy + 60), fill="black", width=3)
    if orientation == "landscape":
        lines = ["NIWA - prova SELPHY P (cartolina)",
                 "Stampa senza bordi, come all'evento.",
                 "Linea tratteggiata: numero a sinistra e a destra.",
                 "Bordo carta: primo numero in alto e in basso."]
    else:
        lines = ["NIWA - prova SELPHY P verticale",
                 "Stampa senza bordi, come all'evento.",
                 "Linea tratteggiata: numero in alto e in basso.",
                 "Bordo carta: primo numero a sinistra e a destra."]
    for index, value in enumerate(lines):
        label((cx, cy - 300 + index * 42 + (60 if index else 0)), value, "black", text)
    label((cx, round((horizontal_reach + 4) * MM)), "ALTO", (20, 90, 220), text)
    label((cx - 250, cy + 120), "SINISTRA", (220, 30, 30), text)
    label((cx + 250, cy + 120), "DESTRA", (220, 30, 30), text)
    return image


if __name__ == "__main__":
    orientation, output = sys.argv[1], sys.argv[2]
    sheet(orientation).save(output, format="JPEG", quality=95, dpi=(300, 300), subsampling=0)
