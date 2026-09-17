"""Catalogue couleur DMC pour le rapprochement Lab (types B/C, Lot 5,
cahier des charges §8.4-8.5).

Contrairement à `app/dmc_colors.py` (type A, Lot 4), où le code DMC est
toujours lu en texte réel dans la légende et où ce module ne sert qu'à
proposer une couleur d'affichage, **aucun texte de légende ne fait autorité
sur la couleur exacte de chaque case** pour les types B/C : la seule source
est la couleur de remplissage du rectangle vectoriel sous chaque case. Il
faut donc, ici, un vrai rapprochement par plus proche voisin perceptuel
(conversion Lab, jamais une distance RVB brute — voir
`.claude/agents/pdf-extraction-specialist.md`) vers une table de référence
suffisamment large.

**Origine des valeurs : table communautaire non officielle.** DMC ne publie
aucune table RVB officielle de ses teintes de mouliné (cahier des charges
§3.3) — les valeurs ci-dessous sont des approximations couramment reprises
par la communauté du point de croix (chartes de conversion DMC -> RVB
largement diffusées par des logiciels et sites communautaires). Elles sont
suffisantes pour une **proposition de départ raisonnable**, jamais pour une
identification garantie exacte : l'étape 7 de l'assistant d'import doit
rester le lieu de correction, et toute correspondance de distance Lab
élevée doit être signalée (voir `nearest_dmc`).
"""

from __future__ import annotations

from dataclasses import dataclass

# Table communautaire code -> (nom, RVB 0-255). Volontairement plus large que
# `app/dmc_colors.py` (qui ne couvre que les codes déjà rencontrés en type A)
# mais toujours partielle : un catalogue DMC complet dépasse 500 teintes et
# reconstruire précisément chacune de mémoire serait pire qu'une table
# raisonnablement large et honnêtement approximative. Un code non couvert ne
# fait simplement pas partie du plus proche voisin possible — comportement
# dégradé mais jamais silencieusement faux (le voisin le plus proche
# disponible est toujours retourné avec sa distance, jamais masquée).
_DMC_CATALOG: dict[str, tuple[str, tuple[int, int, int]]] = {
    # Blancs, écrus, noirs, gris — famille neutre.
    "blanc": ("White", (255, 255, 255)),
    "white": ("White", (255, 255, 255)),
    "b5200": ("Snow White", (255, 255, 255)),
    "ecru": ("Ecru", (240, 234, 218)),
    "3865": ("Winter White", (245, 242, 233)),
    "762": ("Pearl Grey-VY LT", (233, 233, 233)),
    "415": ("Pearl Grey", (211, 211, 211)),
    "318": ("Steel Grey-LT", (171, 171, 171)),
    "414": ("Steel Grey-DK", (140, 140, 140)),
    "317": ("Pewter Grey", (108, 108, 108)),
    "413": ("Pewter Grey-DK", (96, 96, 96)),
    "535": ("Ash Grey-VY LT", (95, 95, 91)),
    "310": ("Black", (5, 5, 5)),
    "3799": ("Pewter Grey-VY DK", (68, 68, 68)),
    # Rouges et roses.
    "666": ("Bright Red", (227, 29, 60)),
    "321": ("Red", (199, 43, 59)),
    "304": ("Red-Medium", (176, 0, 12)),
    "816": ("Garnet", (146, 22, 32)),
    "814": ("Garnet-Dark", (108, 0, 15)),
    "498": ("Red-Dark", (167, 19, 43)),
    "347": ("Salmon-VY Dark", (172, 40, 42)),
    "350": ("Coral-Medium", (222, 91, 74)),
    "351": ("Coral", (240, 122, 100)),
    "352": ("Coral-Light", (252, 153, 133)),
    "353": ("Peach", (254, 210, 195)),
    "3705": ("Melon-Dark", (240, 99, 106)),
    "3706": ("Melon-Medium", (247, 141, 144)),
    "3708": ("Melon-Light", (250, 187, 191)),
    "899": ("Rose-Medium", (222, 128, 141)),
    "957": ("Geranium-Pale", (247, 172, 183)),
    "956": ("Geranium", (243, 108, 130)),
    "3326": ("Rose-Light", (247, 179, 174)),
    "3712": ("Salmon-Medium", (222, 111, 108)),
    "3801": ("Melon-VY Dark", (233, 76, 88)),
    "601": ("Cranberry-Dark", (211, 39, 106)),
    "600": ("Cranberry-VY Dark", (216, 33, 111)),
    "603": ("Cranberry", (245, 130, 175)),
    "604": ("Cranberry-Light", (249, 175, 199)),
    # Oranges.
    "740": ("Tangerine", (255, 140, 0)),
    "741": ("Tangerine-Medium", (255, 160, 35)),
    "742": ("Tangerine-Light", (255, 201, 60)),
    "743": ("Yellow-Medium", (255, 217, 101)),
    "947": ("Burnt Orange", (255, 82, 26)),
    "946": ("Burnt Orange-Medium", (240, 82, 26)),
    "900": ("Burnt Orange-Dark", (215, 62, 0)),
    "608": ("Bright Orange", (253, 91, 39)),
    "721": ("Orange Spice-Medium", (233, 121, 56)),
    "722": ("Orange Spice-Light", (245, 154, 96)),
    "970": ("Pumpkin-Light", (250, 137, 25)),
    "971": ("Pumpkin", (243, 122, 0)),
    # Jaunes.
    "444": ("Lemon-Dark", (255, 208, 0)),
    "445": ("Lemon-Light", (255, 243, 141)),
    "307": ("Lemon", (255, 226, 45)),
    "725": ("Topaz", (255, 199, 62)),
    "726": ("Topaz-Light", (255, 220, 115)),
    "727": ("Topaz-VY LT", (255, 240, 170)),
    "677": ("Old Gold-VY LT", (240, 224, 180)),
    "676": ("Old Gold-Light", (219, 187, 113)),
    "729": ("Old Gold-Medium", (196, 148, 68)),
    "3820": ("Straw-Dark", (218, 165, 32)),
    "3821": ("Straw", (247, 202, 87)),
    "3822": ("Straw-Light", (250, 220, 130)),
    "3823": ("Yellow-Ultra Pale", (255, 250, 220)),
    "834": ("Golden Olive-VY LT", (219, 199, 116)),
    # Verts.
    "700": ("Green-Bright", (0, 122, 40)),
    "701": ("Green-Light", (48, 142, 43)),
    "702": ("Kelly Green", (63, 170, 68)),
    "703": ("Chartreuse", (123, 181, 56)),
    "704": ("Chartreuse-Bright", (155, 202, 63)),
    "699": ("Green", (0, 94, 24)),
    "905": ("Parrot Green-Dark", (95, 133, 31)),
    "906": ("Parrot Green-Medium", (140, 181, 53)),
    "907": ("Parrot Green-Light", (194, 220, 90)),
    "909": ("Emerald Green-VY Dark", (0, 108, 66)),
    "910": ("Emerald Green-Dark", (0, 133, 78)),
    "911": ("Emerald Green-Medium", (0, 153, 89)),
    "912": ("Emerald Green-Light", (0, 175, 110)),
    "913": ("Nile Green-Medium", (85, 191, 130)),
    "954": ("Nile Green", (144, 217, 168)),
    "955": ("Nile Green-Light", (172, 227, 190)),
    "561": ("Jade-VY Dark", (0, 105, 78)),
    "562": ("Jade-Medium", (60, 143, 111)),
    "563": ("Jade-Light", (129, 199, 168)),
    "564": ("Jade-VY Light", (196, 229, 206)),
    "988": ("Forest Green-Medium", (100, 143, 76)),
    "989": ("Forest Green", (127, 169, 89)),
    "3345": ("Hunter Green-Dark", (48, 82, 27)),
    "3346": ("Hunter Green", (80, 114, 57)),
    "3347": ("Yellow Green-Medium", (108, 150, 73)),
    "3348": ("Yellow Green-Light", (185, 205, 130)),
    "471": ("Avocado Green-VY LT", (166, 189, 85)),
    "472": ("Avocado Green-Ultra LT", (216, 226, 157)),
    "470": ("Avocado Green-LT", (135, 160, 72)),
    "469": ("Avocado Green", (110, 130, 56)),
    "320": ("Pistachio Green-Medium", (105, 147, 90)),
    "319": ("Pistachio Green-VY DK", (48, 85, 50)),
    "367": ("Pistachio Green-DK", (98, 133, 88)),
    "368": ("Pistachio Green-Light", (172, 205, 157)),
    "369": ("Pistachio Green-VY LT", (216, 234, 208)),
    "772": ("Yellow Green-VY LT", (223, 233, 199)),
    "3813": ("Blue Green-Light", (163, 205, 191)),
    "3814": ("Aquamarine", (73, 140, 124)),
    "3815": ("Celadon Green-DK", (78, 121, 96)),
    "3816": ("Celadon Green", (110, 152, 121)),
    "3817": ("Celadon Green-LT", (155, 191, 168)),
    "3818": ("Emerald Green-Ultra VY DK", (0, 66, 48)),
    # Bleus.
    "820": ("Royal Blue-VY DK", (17, 40, 118)),
    "796": ("Royal Blue-DK", (26, 58, 128)),
    "797": ("Royal Blue", (30, 77, 148)),
    "798": ("Delft Blue-DK", (68, 108, 168)),
    "799": ("Delft Blue-Medium", (129, 156, 202)),
    "800": ("Delft Blue-Pale", (198, 210, 231)),
    "809": ("Delft Blue", (161, 178, 219)),
    "813": ("Blue-Light", (144, 166, 202)),
    "824": ("Blue-VY Dark", (39, 97, 130)),
    "825": ("Blue-Dark", (52, 118, 155)),
    "826": ("Blue-Medium", (110, 165, 199)),
    "827": ("Blue-VY LT", (192, 222, 234)),
    "828": ("Blue-Ultra VY LT", (215, 234, 238)),
    "930": ("Antique Blue-Dark", (79, 104, 118)),
    "931": ("Antique Blue-Medium", (107, 133, 148)),
    "932": ("Antique Blue-Light", (160, 181, 191)),
    "3325": ("Baby Blue-Light", (188, 211, 230)),
    "334": ("Baby Blue-Medium", (110, 148, 191)),
    "311": ("Navy Blue-Medium", (24, 73, 105)),
    "312": ("Navy Blue-Light", (39, 90, 129)),
    "336": ("Navy Blue", (23, 55, 94)),
    "517": ("Wedgewood-Dark", (52, 116, 139)),
    "518": ("Wedgewood-Light", (86, 148, 168)),
    "519": ("Sky Blue", (140, 190, 205)),
    "3755": ("Baby Blue", (109, 158, 202)),
    "793": ("Cornflower Blue-Medium", (108, 118, 172)),
    "794": ("Cornflower Blue-Light", (152, 166, 204)),
    "156": ("Blue Violet-Medium LT", (144, 150, 195)),
    "157": ("Cornflower Blue-VY LT", (171, 193, 225)),
    "3807": ("Cornflower Blue", (76, 88, 158)),
    "159": ("Grey Blue-LT", (196, 207, 221)),
    "160": ("Grey Blue-Medium", (141, 160, 188)),
    "161": ("Grey Blue", (123, 147, 180)),
    # Turquoises / verts bleutés.
    "996": ("Electric Blue-Medium", (0, 168, 220)),
    "3843": ("Electric Blue", (0, 176, 197)),
    "3846": ("Bright Turquoise-LT", (52, 198, 219)),
    "807": ("Peacock Blue", (99, 168, 177)),
    "3766": ("Peacock Blue-Light", (62, 147, 168)),
    "992": ("Aquamarine-Light", (85, 191, 169)),
    "993": ("Aquamarine-VY LT", (169, 224, 208)),
    "964": ("Sea Green-Light", (176, 226, 216)),
    "943": ("Aquamarine-Medium", (0, 148, 132)),
    # Violets / mauves.
    "333": ("Blue Violet-VY DK", (85, 65, 122)),
    "340": ("Blue Violet-Medium", (150, 145, 197)),
    "341": ("Blue Violet-Light", (172, 174, 213)),
    "155": ("Blue Violet-Medium DK", (109, 100, 158)),
    "552": ("Violet-Medium", (110, 46, 116)),
    "553": ("Violet", (150, 91, 155)),
    "554": ("Violet-Light", (211, 172, 211)),
    "208": ("Lavender-VY DK", (128, 88, 140)),
    "209": ("Lavender-Dark", (161, 122, 171)),
    "210": ("Lavender-Medium", (191, 156, 199)),
    "211": ("Lavender-Light", (223, 202, 224)),
    "327": ("Violet-Dark", (86, 41, 87)),
    "3837": ("Lavender-Ultra Dark", (100, 45, 105)),
    "3746": ("Blue Violet-Dark", (120, 106, 172)),
    # Roses violacés / magentas.
    "718": ("Plum", (150, 26, 99)),
    "917": ("Plum-Medium", (161, 41, 106)),
    "915": ("Plum-Dark", (125, 5, 71)),
    "3609": ("Plum-Ultra Light", (233, 158, 210)),
    "3608": ("Plum-Very Light", (216, 124, 184)),
    "3607": ("Plum-Light", (190, 71, 140)),
    # Bruns / beiges.
    "300": ("Mahogany-VY Dark", (123, 63, 0)),
    "301": ("Mahogany-Medium", (181, 97, 50)),
    "400": ("Mahogany-Dark", (147, 75, 25)),
    "402": ("Mahogany-VY LT", (240, 170, 125)),
    "434": ("Brown-Light", (150, 96, 47)),
    "435": ("Brown-VY Light", (176, 122, 62)),
    "436": ("Tan", (196, 148, 82)),
    "437": ("Tan-Light", (226, 186, 133)),
    "438": ("Tan-VY Dark", (135, 90, 39)),
    "801": ("Coffee Brown-DK", (94, 58, 30)),
    "839": ("Beige Brown-DK", (90, 74, 58)),
    "840": ("Beige Brown-Medium", (140, 115, 85)),
    "841": ("Beige Brown-Light", (188, 165, 137)),
    "842": ("Beige Brown-VY LT", (222, 205, 184)),
    "838": ("Beige Brown-VY Dark", (60, 48, 36)),
    "938": ("Coffee Brown-Ultra Dark", (55, 32, 24)),
    "610": ("Drab Brown-Dark", (117, 92, 62)),
    "611": ("Drab Brown", (140, 112, 79)),
    "612": ("Drab Brown-Light", (176, 148, 110)),
    "613": ("Drab Brown-VY Light", (223, 205, 182)),
    "3031": ("Mocha Brown-VY Dark", (75, 52, 35)),
    "3032": ("Mocha Brown-Medium", (183, 155, 121)),
    "3033": ("Mocha Brown-VY LT", (237, 224, 202)),
    "3781": ("Mocha Brown-DK", (89, 65, 46)),
    "3782": ("Mocha Brown-Light", (203, 178, 145)),
    "3790": ("Beige Grey-Ultra DK", (114, 96, 79)),
    "3861": ("Cocoa-Light", (166, 130, 106)),
    "3862": ("Mocha Beige-Dark", (122, 95, 68)),
    "3863": ("Mocha Beige-Medium", (150, 118, 89)),
    "3864": ("Mocha Beige-Light", (196, 172, 145)),
    "640": ("Beige Grey-VY DK", (131, 113, 86)),
    "642": ("Beige Grey-Dark", (147, 128, 95)),
    "644": ("Beige Grey-Medium", (218, 207, 184)),
    "645": ("Beige Grey-VY DK", (109, 105, 96)),
    "646": ("Beige Grey-Dark", (127, 123, 113)),
    "647": ("Beige Grey-Medium", (150, 146, 135)),
    "648": ("Beige Grey-Light", (185, 181, 168)),
    "738": ("Tan-VY LT", (237, 201, 150)),
    "739": ("Tan-Ultra VY LT", (247, 228, 197)),
    "3021": ("Brown Grey-VY DK", (77, 66, 62)),
    "3022": ("Brown Grey-Medium", (147, 138, 125)),
    "3023": ("Brown Grey-Light", (185, 176, 157)),
    "3024": ("Brown Grey-VY LT", (223, 220, 211)),
    "422": ("Hazelnut Brown-LT", (172, 128, 84)),
    "3776": ("Mahogany-Light", (198, 119, 79)),
    "3826": ("Golden Brown", (167, 82, 38)),
    "3827": ("Golden Brown-Pale", (232, 180, 116)),
    "3852": ("Straw-VY Dark", (196, 152, 21)),
    "3853": ("Autumn Gold-Dark", (240, 128, 62)),
    "3854": ("Autumn Gold-Medium", (240, 158, 95)),
    "3855": ("Autumn Gold-Light", (247, 202, 138)),
    "3856": ("Mahogany-Ultra VY LT", (250, 206, 160)),
    "976": ("Golden Brown-Medium", (204, 121, 46)),
    "977": ("Golden Brown-Light", (222, 154, 84)),
    # Métallisés / effets (repli neutre, teinte dominante approximée).
    "e321": ("Light Effects-Red", (196, 30, 58)),
    "e301": ("Light Effects-Gold", (212, 175, 55)),
    "e168": ("Light Effects-Silver", (200, 200, 205)),
    "e3852": ("Light Effects-Gold Dark", (180, 140, 40)),
    "e703": ("Light Effects-Green", (110, 170, 70)),
    "e747": ("Light Effects-Blue", (150, 190, 210)),
}


@dataclass(frozen=True)
class DmcMatch:
    code: str
    """Code tel qu'imprimé (casse d'origine de `_DMC_CATALOG`, souvent en
    minuscule pour les codes lettrés comme `e321` — laisser tel quel plutôt
    que de deviner une capitalisation « officielle »)."""

    name: str
    rgb_hex: str
    distance: float
    """Distance perceptuelle Lab (CIE76) entre la couleur demandée et
    `rgb_hex` — jamais une distance RVB brute (règle impérative du
    `pdf-extraction-specialist`). 0 = correspondance exacte, au-delà d'une
    dizaine d'unités l'œil perçoit une différence nette."""


def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return float(((channel + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """`rgb` en composantes 0-1. Conversion sRGB -> CIE Lab (D65), utilisée
    pour toute comparaison perceptuelle de couleur dans le moteur
    d'extraction (jamais de distance RVB brute)."""
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t: float) -> float:
        if t > 0.008856:
            return float(t ** (1.0 / 3.0))
        return 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    lightness = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    return lightness, a, bb


def lab_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Distance euclidienne en espace Lab (CIE76) — approximation simple
    mais largement suffisante pour classer des teintes de mouliné, qui sont
    rarement dans les zones où CIE76 diverge le plus de la perception
    (saturation extrême)."""
    return float(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5)


_CATALOG_LAB: dict[str, tuple[float, float, float]] = {
    code: rgb_to_lab((r / 255, g / 255, b / 255)) for code, (_, (r, g, b)) in _DMC_CATALOG.items()
}


def rgb_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def nearest_dmc(rgb: tuple[float, float, float]) -> DmcMatch:
    """Plus proche voisin dans `_DMC_CATALOG` pour `rgb` (composantes 0-1),
    par distance Lab. Toujours renvoie une correspondance (jamais `None` —
    le catalogue n'est jamais vide) ; c'est à l'appelant de décider, via
    `DmcMatch.distance`, si elle est assez fiable pour ne pas être signalée
    à l'utilisateur (cahier des charges §8.5 : « toute correspondance
    au-delà d'un seuil est signalée »)."""
    target = rgb_to_lab(rgb)
    best_code: str | None = None
    best_distance = float("inf")
    for code, lab in _CATALOG_LAB.items():
        distance = lab_distance(target, lab)
        if distance < best_distance:
            best_distance = distance
            best_code = code
    assert best_code is not None  # le catalogue n'est jamais vide
    name, rgb_int = _DMC_CATALOG[best_code]
    return DmcMatch(code=best_code, name=name, rgb_hex=rgb_hex(rgb_int), distance=best_distance)
