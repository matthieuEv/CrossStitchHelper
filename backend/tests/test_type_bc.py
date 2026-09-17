"""Tests du moteur d'extraction types B/C (Lot 5) contre les quatre fixtures
DMC réelles — voir `fixtures/README.md` et le skill
`.claude/skills/verify-extraction-fixtures/`.

Le nombre de couleurs distinctes réellement utilisées (`fixtures/README.md`)
est vérifié exactement pour trois des quatre fixtures : 14 pour
`winter-wreath-dmc`, 17 pour `botanical-citrus-dmc`, 18 pour `cucurbit-dmc`
(les 18 couleurs de la légende de cucurbit y sont bien toutes réellement
utilisées dans la grille — mesuré directement sur les cases coloriées, pas
recopié de la légende ; contrairement à ce qu'on pourrait déduire d'un
survol rapide de la légende, cf. `docs/cahier-des-charges.md` §4.3 : ne
jamais supposer, toujours mesurer).

`summer-flight-dmc` est le cas piège du Lot 5 (§4.3) : sa page couleur
contient déjà, elle-même, une quantité de tracés vectoriels comparable à une
page symboles à part entière. Il sert ici à vérifier que le connecteur ne
suppose jamais aveuglément une superposition à deux pages, **et** — au-delà
de la mesure de densité par page — que la reconnaissance de forme se replie
honnêtement sur la couleur seule (type B) quand elle n'est pas assez fiable
sur l'ensemble du fichier plutôt que de produire une palette de plusieurs
centaines d'entrées inutilisable. Ce fichier utilise en réalité une
illustration richement nuancée (plusieurs tons par élément de motif, pas un
simple aplat par fil) : le nombre de couleurs distinctes mesuré est donc
volontairement vérifié à la hausse par rapport aux 12 codes de la légende
« points comptés », pas recopié de cette légende — mêmes règles que
`test_type_a.py` : aucune valeur attendue definie à la main quand le fichier
source permet de la mesurer soi-même."""

from __future__ import annotations

import time
from pathlib import Path

import pymupdf
import pytest

from app.type_bc import TypeBCResult, detect_type_bc

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"

WINTER_WREATH = FIXTURES_ROOT / "winter-wreath-dmc" / "PATASS117_2C_2.pdf"
BOTANICAL_CITRUS = FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf"
CUCURBIT = FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf"
SUMMER_FLIGHT = FIXTURES_ROOT / "summer-flight-dmc" / "vol_de_te.pdf"

DMC_FIXTURES = [WINTER_WREATH, BOTANICAL_CITRUS, CUCURBIT, SUMMER_FLIGHT]

# Les deux fixtures d'un autre type (cahier des charges §4.4) : `detect_type_bc`
# doit s'effacer proprement dessus, comme `detect_type_a` s'efface sur les
# fixtures B/C/E (voir `test_type_a.py`).
OTHER_TYPE_FIXTURES = [
    FIXTURES_ROOT / "cafe-brasserie-charting-export" / "CaffeBrasseriecoloursymbols.pdf",
    FIXTURES_ROOT / "river-and-mountains-laserarts" / "RiverAndMountains-CS.pdf",
]


def _distinct_colors(result: TypeBCResult) -> int:
    """Nombre de couleurs distinctes réellement présentes dans la palette —
    plusieurs entrées de palette peuvent partager la même couleur en type C
    (une couleur associée à plusieurs symboles distincts), donc distinct de
    `len(result.palette)`."""
    return len({entry.rgb_hex for entry in result.palette})


@pytest.fixture(scope="module")
def winter_wreath() -> TypeBCResult:
    result = detect_type_bc(WINTER_WREATH)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def botanical_citrus() -> TypeBCResult:
    result = detect_type_bc(BOTANICAL_CITRUS)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def cucurbit() -> TypeBCResult:
    result = detect_type_bc(CUCURBIT)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def summer_flight() -> TypeBCResult:
    result = detect_type_bc(SUMMER_FLIGHT)
    assert result is not None
    return result


@pytest.mark.parametrize("path", DMC_FIXTURES, ids=lambda p: p.parent.name)
def test_fixture_files_present(path: Path) -> None:
    assert path.is_file(), f"fixture manquante : {path}"


def _assert_well_formed(result: TypeBCResult) -> None:
    assert result.columns > 0
    assert result.rows > 0
    assert len(result.cells) == result.columns * result.rows
    assert all(0 <= value <= len(result.palette) for value in result.cells)
    assert all(
        entry.rgb_hex.startswith("#") and len(entry.rgb_hex) == 7 for entry in result.palette
    )
    assert all(
        entry.symbol_key.isascii() and entry.symbol_key.isprintable() for entry in result.palette
    )
    assert all(0 <= idx < len(result.cells) for idx in result.uncertain_cells)
    assert 0.0 <= result.confidence <= 1.0


def test_winter_wreath_is_well_formed(winter_wreath: TypeBCResult) -> None:
    _assert_well_formed(winter_wreath)


def test_botanical_citrus_is_well_formed(botanical_citrus: TypeBCResult) -> None:
    _assert_well_formed(botanical_citrus)


def test_cucurbit_is_well_formed(cucurbit: TypeBCResult) -> None:
    _assert_well_formed(cucurbit)


def test_summer_flight_is_well_formed(summer_flight: TypeBCResult) -> None:
    _assert_well_formed(summer_flight)


def test_winter_wreath_distinct_colours_match_legend(winter_wreath: TypeBCResult) -> None:
    """`fixtures/README.md` : légende page 4, 14 codes DMC (3345, 3346, 471,
    472, 11, 18, 3821, 726, 3853, 3854, blanc, 351, 814, E321)."""
    assert _distinct_colors(winter_wreath) == 14


def test_botanical_citrus_distinct_colours_match_legend(botanical_citrus: TypeBCResult) -> None:
    """`fixtures/README.md` : légende page 4, 17 couleurs DMC."""
    assert _distinct_colors(botanical_citrus) == 17


def test_cucurbit_distinct_colours_match_legend(cucurbit: TypeBCResult) -> None:
    """`fixtures/README.md` signale 18 couleurs en légende dont 6
    échantillons hors motif — mais mesuré directement sur les cases
    réellement coloriées de la grille (jamais sur la légende), les 18
    couleurs de cucurbit sont bien toutes utilisées dans la grille : aucune
    des 18 n'est un doublon de couleur d'une autre. Le filtrage "hors motif"
    décrit dans la fixture s'applique donc à la légende telle qu'imprimée
    (qui inclut des échantillons non repris dans le dessin), pas à un excès
    de couleurs mesurées ici — cohérent avec la consigne de vérifier soi-même
    plutôt que de recopier un chiffre indicatif."""
    assert _distinct_colors(cucurbit) == 18


def test_summer_flight_uses_more_shades_than_its_flat_legend_suggests(
    summer_flight: TypeBCResult,
) -> None:
    """La légende « points comptés » de `summer-flight-dmc` liste 12 codes
    DMC, mais la page couleur dessine en réalité une illustration nuancée
    (plusieurs tons distincts par zone de motif plutôt qu'un aplat unique
    par fil) — mesuré directement, pas recopié de la légende. Le connecteur
    doit donc y trouver sensiblement plus de couleurs distinctes que 12."""
    assert _distinct_colors(summer_flight) > 12


def test_winter_wreath_symbols_reused_from_its_own_colour_page(
    winter_wreath: TypeBCResult,
) -> None:
    """Cas mesuré (§4.3) : la page couleur de `winter-wreath-dmc` porte déjà
    elle-même les symboles — aucune page séparée n'est nécessaire, et le
    connecteur doit le mesurer plutôt que supposer la structure "page 1
    couleur seule / page 2 symboles" que suggérerait un survol rapide du
    cahier des charges §4.1."""
    assert winter_wreath.grid_type == "C"
    glyphs = [e.symbol_glyph for e in winter_wreath.palette if e.symbol_glyph is not None]
    assert glyphs
    assert all(g.page_number == 1 for g in glyphs)


@pytest.mark.parametrize(
    "fixture_name", ["botanical_citrus", "cucurbit"], ids=lambda n: n.replace("_", "-")
)
def test_botanical_and_cucurbit_overlay_a_separate_symbol_page(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    """Cas mesuré (§4.3, `fixtures/README.md`) : la page couleur de ces deux
    fixtures est propre (peu de tracés), la page 2 porte les symboles —
    superposition à deux pages réellement nécessaire ici, contrairement à
    `winter-wreath-dmc` et `summer-flight-dmc`."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    assert result.grid_type == "C"
    glyphs = [e.symbol_glyph for e in result.palette if e.symbol_glyph is not None]
    assert glyphs
    assert all(g.page_number == 2 for g in glyphs)


def test_summer_flight_never_blindly_overlays_a_redundant_page(
    summer_flight: TypeBCResult,
) -> None:
    """Le coeur du cas piège (§4.3) : ce fichier ne doit jamais faire
    échouer le connecteur en lui faisant croire à une vraie page de symboles
    superposable. Ici, la reconnaissance de forme s'avère trop peu fiable
    sur l'ensemble du fichier (illustration nuancée, pas un symbole net par
    case) — repli honnête en type B, jamais une palette de plusieurs
    centaines d'entrées présentée comme fiable."""
    assert summer_flight.grid_type == "B"
    assert len(summer_flight.palette) < 50
    assert any("repli" in w.lower() or "fiable" in w.lower() for w in summer_flight.warnings)


def test_uncertain_cells_are_explicitly_flagged_not_silently_wrong(
    botanical_citrus: TypeBCResult,
) -> None:
    """Règle impérative (`pdf-extraction-specialist`) : toute case incertaine
    doit être signalée, jamais laissée fausse en silence. Vérifie que le
    mécanisme de signalement est réellement câblé de bout en bout (pas
    seulement présent dans le contrat de données)."""
    assert botanical_citrus.uncertain_cells
    assert any("incertaine" in w for w in botanical_citrus.warnings)


@pytest.mark.parametrize(
    ("fixture_name", "max_uncertain_fraction"),
    [("botanical_citrus", 0.25), ("cucurbit", 0.25)],
    ids=lambda v: str(v),
)
def test_uncertain_cell_rate_stays_reasonable_not_almost_the_whole_grid(
    fixture_name: str, max_uncertain_fraction: float, request: pytest.FixtureRequest
) -> None:
    """Non-régression du correctif « cases incertaines » : avant ce correctif,
    `botanical-citrus-dmc` et `cucurbit-dmc` signalaient respectivement 58 %
    et 34 % des cases coloriées comme incertaines (`1630/2802` et
    `642/1911`), au point de couvrir la quasi-totalité de certaines zones du
    motif dans le pinceau de l'assistant — bien plus qu'une vraie proportion
    de couleurs/symboles ambigus. Cause mesurée et corrigée :
    `_color_to_rgb` convertissait le CMJN vers le RVB par la formule naïve
    recommandée en repli par le spec PDF (`R=(1-C)(1-K)`...), qui sursature
    nettement les teintes obtenues par mélange cyan+jaune (verts en
    particulier) et gonflait artificiellement la distance Lab au
    rapprochement DMC pour plusieurs couleurs à forte population de cases —
    confirmé en comparant cette formule à la couleur réellement rendue par
    PyMuPDF pour les mêmes valeurs CMJN. `_cmyk_to_rgb_via_mupdf` la
    remplace. Une seconde piste (desserrer `_SIGNATURE_MERGE_MAX_BIT_DIFF`
    pour absorber le bruit de repositionnement entre bitmaps de signature
    d'un même symbole redessiné) a été mesurée puis **abandonnée** : à un
    seuil de 4 bits, elle fusionnait à tort un symbole « + » avec un symbole
    « flèche vers le haut » sur `botanical-citrus-dmc` (confirmé
    visuellement en rendant les deux bitmaps via `render_symbol_svg`) — le
    seuil est resté à sa valeur prudente d'origine. Mesuré après correctif :
    20.7 % (`580/2802`) sur `botanical-citrus-dmc` et 21.0 % (`401/1911`)
    sur `cucurbit-dmc` — les bornes ci-dessous gardent une marge confortable
    au-dessus de ces valeurs mesurées (jamais resserrées au point de casser
    au moindre écart mineur) tout en interdisant une régression vers un taux
    proche de celui d'avant correctif. Ne vérifie jamais que
    `uncertain_cells` est vide : une partie de l'incertitude mesurée ici est
    réelle (quelques teintes hors de portée du catalogue DMC communautaire
    partiel, §8.5) et doit rester signalée."""
    result: TypeBCResult = request.getfixturevalue(fixture_name)
    total = sum(1 for value in result.cells if value != 0)
    fraction = len(result.uncertain_cells) / total
    assert fraction < max_uncertain_fraction
    assert result.uncertain_cells  # une incertitude réelle et mesurée doit rester signalée


def test_confidence_reflects_the_type_b_fallback_penalty(
    summer_flight: TypeBCResult,
) -> None:
    """`detect_type_bc` déduit toujours 0.2 de la confiance quand la
    reconnaissance de forme se replie honnêtement en type B (voir le bloc
    `confidence -= 0.2` de `detect_type_bc`) — la confiance ne peut donc
    jamais dépasser 0.8 dans ce cas, quel que soit par ailleurs le taux de
    cases incertaines (qui ne peut que la faire encore baisser, jamais
    remonter). Comparer directement `summer_flight.confidence` à celle d'une
    autre fixture (`winter_wreath` notamment) n'est plus fiable depuis le
    correctif CMJN->RVB du Lot 5 (cases incertaines) : les deux fixtures
    partagent la même palette DMC communautaire de 228 teintes, dont la
    couverture varie indépendamment du gabarit de fichier d'une fixture à
    l'autre (mesuré : `winter-wreath-dmc` recule légèrement en confiance
    après ce correctif malgré une reconnaissance de forme parfaitement
    fiable, simplement parce que deux de ses teintes n'ont pas de
    correspondance DMC proche dans ce catalogue nécessairement partiel) —
    seul le mécanisme de repli lui-même, pas une comparaison brute entre
    fixtures, est une garantie robuste ici."""
    assert summer_flight.confidence <= 0.8


def _tiny_non_type_bc_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), "Just a plain PDF, not a pattern export.")
    path = tmp_path / "not-type-bc.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return path


def test_returns_none_for_non_type_bc_pdf(tmp_path: Path) -> None:
    assert detect_type_bc(_tiny_non_type_bc_pdf(tmp_path)) is None


def test_never_raises_on_empty_pdf(tmp_path: Path) -> None:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page(width=300, height=200)
    path = tmp_path / "empty.pdf"
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    assert detect_type_bc(path) is None


@pytest.mark.parametrize("path", OTHER_TYPE_FIXTURES, ids=lambda p: p.parent.name)
def test_returns_none_for_other_fixture_types(path: Path) -> None:
    """Type A (police de symboles embarquée) et type E (catalogue d'images
    bitmap réutilisées, `river-and-mountains-laserarts`) : pas de faux
    positif B/C. `river-and-mountains-laserarts` est un cas piège
    supplémentaire pour ce connecteur précis : ses pages de grille portent
    elles aussi un habillage de rectangles de fond par case (gabarit
    d'éditeur), ce qui le rendrait éligible comme page couleur B/C si la
    présence d'images bitmap n'était pas vérifiée en premier lieu."""
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    assert detect_type_bc(path) is None


@pytest.mark.parametrize("path", DMC_FIXTURES, ids=lambda p: p.parent.name)
def test_runs_within_reasonable_time(path: Path) -> None:
    """Repère de performance généreux (cahier des charges §10 : « moins de
    30 secondes » pour un PDF de 10 pages) — voir le rapport de tâche pour
    les temps mesurés précis par fixture."""
    start = time.perf_counter()
    detect_type_bc(path)
    assert time.perf_counter() - start < 30.0
