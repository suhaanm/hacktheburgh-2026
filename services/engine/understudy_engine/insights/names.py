"""Invented, realistic full names for the SYNTHETIC firm (REQ-9, owner decision: the demo firm shows human-looking names, not codes). Display only: nothing in the selection,
the thresholds or the evaluation reads a name, and ``label`` stays the stable id and the sort key.

The list and the rule are the dashboard's own (``apps/dashboard/scripts/name-fixtures.mjs``), copied verbatim so the engine and the example data agree:

1. take every person label ("BP-07", "DA-02", "PG-11") in the firm, sorted in natural order (digits compare as numbers);
2. for each label in that order, start at ``FNV-1a-32(label) mod len(NAMES)`` and step forward (wrapping) to the first name no earlier label took;
3. a name is therefore never reused inside one firm (the list has 100 names; a firm with more people than that names the first 100 in label order and leaves the rest
   with no name, which the screens show as the label).

The names are made up (first and last names from many backgrounds, paired by hand to avoid anyone well known); they name no real person. They are given only to the synthetic
firm: a ``local`` ledger belongs to a real person and gets no invented name.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

NAMES: tuple[str, ...] = (
    "Amara Okafor", "Tomasz Wrobel", "Priya Raghunathan", "Mateo Salazar", "Hana Kobayashi", "Dmitri Voronin", "Fatima Al-Sayed", "Kwame Mensah",
    "Ingrid Lindqvist", "Rohan Deshpande", "Leila Haddad", "Joaquin Echeverria", "Mei Tan", "Oluwaseun Adebayo", "Siobhan Gallagher",
    "Anders Nystrom", "Yara Karimi", "Kenji Matsuda", "Thandiwe Dlamini", "Marek Kowalczyk", "Noor Rahimi", "Cormac Brennan", "Esperanza Villanueva",
    "Ravi Menon", "Katarzyna Nowak", "Idris Bello", "Freya Holloway", "Santiago Cardoso", "Aiko Yamamoto", "Emeka Eze", "Ottilie Pemberton",
    "Tariq Rashid", "Lucia Ferrero", "Bao Nguyen", "Ayesha Qureshi", "Henrik Halvorsen", "Zainab Abubakar", "Rhys Llewellyn", "Imani Boateng",
    "Pavel Novak", "Sunita Iyer", "Declan Quinn", "Mariam Sesay", "Takeshi Morita", "Gwen Hartley", "Abdullahi Warsame", "Elodie Marchetti",
    "Vikram Subramanian", "Nadia Petrova", "Fergus Lowry", "Chiamaka Obi", "Luca Bianchi", "Soo-jin Han", "Bartosz Zielinski", "Anjali Kulkarni",
    "Kofi Asante", "Maren Bjornsen", "Hamza Chaudhry", "Isla Mackenzie", "Rafael Quintero", "Wanjiru Kamau", "Stellan Berg", "Parisa Tehrani",
    "Eoin Doyle", "Adaeze Nwosu", "Matthias Keller", "Lakshmi Pillai", "Dara Sheridan", "Yusuf Demir", "Greta Lindgren", "Arjun Bhatt",
    "Ximena Ortega", "Cian Maguire", "Halima Suleiman", "Jonas Eriksen", "Meera Joshi", "Osei Appiah", "Tamsin Ridley", "Nikolai Sokolov",
    "Farah Siddiqui", "Ewan Calder", "Beatriz Lacerda", "Sandeep Grewal", "Ilse Vandermeer", "Jamal Whitfield", "Orla Keane", "Kazuki Fujimoto",
    "Branwen Pryce", "Mustafa Aydin", "Daria Kovac", "Ansel Thorne", "Chidi Okonkwo", "Rania Khoury", "Tobias Lehmann", "Nkechi Umeh",
    "Lorcan Mulvey", "Selin Yildiz", "Anil Reddy", "Briony Castle", "Emre Kaya",
)

_FNV_OFFSET, _FNV_PRIME = 0x811C9DC5, 0x01000193
_CHUNK = re.compile(r"(\d+)")


def fnv1a(s: str) -> int:
    """FNV-1a, 32 bit, over the UTF-16 code units of ``s`` (what the dashboard's ``charCodeAt`` sees; labels are ASCII)."""
    h = _FNV_OFFSET
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * _FNV_PRIME) & 0xFFFFFFFF
    return h


def natural_key(label: str) -> tuple:
    """Natural order like ``localeCompare(b, "en", {numeric: true})`` for labels of the form LETTERS-DIGITS: letters compare ignoring case, digit runs as numbers."""
    return tuple((0, int(c)) if c.isdigit() else (1, c.lower()) for c in _CHUNK.split(label) if c != "")


def assign_names(labels: Iterable[str]) -> dict[str, str]:
    """``label -> name`` for one firm, by the rule above. Deterministic in the set of labels (the order they are given in never matters)."""
    sorted_labels = sorted(set(labels), key=natural_key)
    taken: set[int] = set()
    out: dict[str, str] = {}
    for label in sorted_labels:
        if len(taken) >= len(NAMES):
            break
        i = fnv1a(label) % len(NAMES)
        while i in taken:
            i = (i + 1) % len(NAMES)
        taken.add(i)
        out[label] = NAMES[i]
    return out
