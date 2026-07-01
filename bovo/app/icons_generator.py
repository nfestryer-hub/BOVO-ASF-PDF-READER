"""Générateur d'icônes vectorielles PIL pour la sidebar Bovo ASF Manager.

Chaque fonction dessine une icône SVG-like dans un canevas transparent
32×32 et l'enregistre dans ``assets/icons/{name}.png`` puis
``assets/icons/{name}@white.png`` (variante blanche pour état actif).

Exécution : ``python -m app.icons_generator`` — s'exécute une seule fois,
au moment de la génération des livrables. Les PNG produits sont ensuite
livrés avec l'application (pas de dépendance runtime au dessin).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
SIZE = 64                 # rendu HDPI pour qualité maximale
STROKE = 4                # épaisseur des traits
ACCENT_RGB = (230, 57, 70)  # Rouge BOVO
WHITE_RGB = (255, 255, 255)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Crée un canevas RGBA transparent 64×64."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


# ---------------------------------------------------------------------- #
# Dessins vectoriels — 1 fonction par icône
# ---------------------------------------------------------------------- #
def _home(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    # Toit + murs (maison stylisée)
    draw.polygon([(32, 8), (58, 30), (52, 30), (52, 54), (36, 54), (36, 40),
                  (28, 40), (28, 54), (12, 54), (12, 30), (6, 30)],
                 outline=color, width=STROKE)


def _calendar(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((8, 12, 56, 56), radius=6, outline=color, width=STROKE)
    draw.line((8, 24, 56, 24), fill=color, width=STROKE)
    draw.line((20, 6, 20, 18), fill=color, width=STROKE)
    draw.line((44, 6, 44, 18), fill=color, width=STROKE)
    # Petites cases
    for row in range(2):
        for col in range(3):
            x, y = 16 + col * 12, 32 + row * 10
            draw.rectangle((x, y, x + 6, y + 5), outline=color, width=2)


def _search(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    draw.ellipse((10, 10, 42, 42), outline=color, width=STROKE)
    draw.line((38, 38, 54, 54), fill=color, width=STROKE + 1)


def _tools(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    # Clé (wrench) diagonale
    draw.polygon([(8, 46), (18, 56), (46, 28), (52, 34), (58, 20), (44, 14),
                  (50, 20), (24, 46), (14, 36)], outline=color, width=STROKE)


def _document(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    draw.polygon([(14, 6), (40, 6), (54, 20), (54, 58), (14, 58)],
                 outline=color, width=STROKE)
    draw.polygon([(40, 6), (40, 20), (54, 20)], outline=color, width=STROKE)
    draw.line((22, 34, 46, 34), fill=color, width=STROKE - 1)
    draw.line((22, 44, 46, 44), fill=color, width=STROKE - 1)


def _upload(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    # Flèche vers le haut + barre de base
    draw.line((32, 12, 32, 44), fill=color, width=STROKE + 1)
    draw.polygon([(32, 8), (18, 22), (46, 22)], outline=color, width=STROKE, fill=color)
    draw.line((14, 52, 50, 52), fill=color, width=STROKE + 1)


def _clock(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    draw.ellipse((8, 8, 56, 56), outline=color, width=STROKE)
    draw.line((32, 32, 32, 18), fill=color, width=STROKE)
    draw.line((32, 32, 44, 38), fill=color, width=STROKE)


def _users(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    # Deux personnes stylisées
    draw.ellipse((10, 12, 26, 28), outline=color, width=STROKE)
    draw.arc((6, 26, 30, 52), start=180, end=0, fill=color, width=STROKE)
    draw.ellipse((36, 8, 56, 28), outline=color, width=STROKE)
    draw.arc((30, 24, 60, 58), start=180, end=0, fill=color, width=STROKE)


def _journal(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    draw.rectangle((12, 8, 52, 56), outline=color, width=STROKE)
    draw.line((20, 20, 44, 20), fill=color, width=STROKE - 1)
    draw.line((20, 30, 44, 30), fill=color, width=STROKE - 1)
    draw.line((20, 40, 44, 40), fill=color, width=STROKE - 1)
    draw.line((20, 50, 34, 50), fill=color, width=STROKE - 1)


def _settings(draw: ImageDraw.ImageDraw, color: tuple[int, int, int]) -> None:
    # Engrenage simplifié : cercle + 8 dents
    cx, cy, r = 32, 32, 18
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=STROKE)
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=color, width=STROKE)
    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        from math import cos, radians, sin
        rad = radians(angle)
        x1, y1 = cx + int(r * cos(rad)), cy + int(r * sin(rad))
        x2, y2 = cx + int((r + 8) * cos(rad)), cy + int((r + 8) * sin(rad))
        draw.line((x1, y1, x2, y2), fill=color, width=STROKE + 1)


ICONS: dict[str, callable] = {
    "home": _home,
    "calendar": _calendar,
    "search": _search,
    "tools": _tools,
    "document": _document,
    "upload": _upload,
    "clock": _clock,
    "users": _users,
    "journal": _journal,
    "settings": _settings,
}


def generate_all() -> None:
    """Génère toutes les icônes en variante accent + blanche."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    for name, painter in ICONS.items():
        for color, suffix in ((ACCENT_RGB, ""), (WHITE_RGB, "@white")):
            image, draw = _canvas()
            painter(draw, color)
            path = ICONS_DIR / f"{name}{suffix}.png"
            image.save(path, "PNG", optimize=True)
            print(f"✓ {path.name}")


if __name__ == "__main__":
    generate_all()
