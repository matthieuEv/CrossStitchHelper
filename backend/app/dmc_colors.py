"""Table de référence couleur → fil DMC (cahier des charges §8.5).

Pour le type A (`app/type_a.py`), la légende du PDF donne le code DMC en
texte réel — il fait foi, ce module ne sert donc **pas** à un rapprochement
par distance colorimétrique ici (ça, c'est le type B/C, Lot 5). Son seul rôle
est de fournir une couleur d'affichage approximative pour l'interface : le
PDF ne transmet aucune valeur RVB explicite pour chaque fil, seulement son
nom et son code.

Volontairement limité aux codes rencontrés jusqu'ici plutôt qu'un catalogue
DMC complet reconstruit de mémoire (risque d'erreurs non vérifiables) — un
code absent de cette table est un cas géré explicitement (`dmc_hex` renvoie
`None`), jamais une couleur inventée en silence (règle impérative du
`pdf-extraction-specialist`, voir `.claude/agents/`).
"""

from __future__ import annotations

# Approximations RVB usuelles pour l'affichage — jamais utilisées pour
# identifier une couleur, seulement pour la représenter à l'écran une fois le
# code déjà connu via le texte de la légende.
_DMC_HEX: dict[str, str] = {
    "157": "#abc1e1",
    "159": "#c4cfdd",
    "160": "#8da0bc",
    "161": "#7b93b4",
    "300": "#7b3f00",
    "301": "#b56132",
    "304": "#b0000c",
    "310": "#050505",
    "402": "#f0aa7d",
    "413": "#66686c",
    "608": "#fd5b27",
    "613": "#dfcdb6",
    "640": "#837156",
    "642": "#93805f",
    "666": "#e31d3c",
    "740": "#ff8c00",
    "741": "#ffa023",
    "742": "#ffc93c",
    "743": "#ffd965",
    "762": "#e9e9e9",
    "793": "#5c71ad",
    "794": "#8fa3d3",
    "814": "#6c000f",
    "839": "#5a4a3a",
    "840": "#8c7355",
    "938": "#372018",
    "946": "#f0521a",
    "3031": "#4b3423",
    "3756": "#e6f0f7",
    "3766": "#3e93a8",
    "3776": "#c6774f",
    "3856": "#f5c9a0",
    "b5200": "#ffffff",
}

FALLBACK_HEX = "#9a9a9a"
"""Gris neutre pour un code inconnu de la table — jamais une couleur
inventée à partir du nom : la présence de ce code dans le résultat doit
toujours s'accompagner d'un avertissement de confiance côté appelant."""


def dmc_hex(code: str) -> str | None:
    """`None` si le code n'est pas dans la table — à l'appelant de le
    signaler plutôt que de masquer le manque derrière `FALLBACK_HEX`."""
    return _DMC_HEX.get(code.strip().lower())
