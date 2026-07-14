"""Export the public methodology manifest for the static viewer.

The output is intentionally byte-stable: no timestamps and sorted JSON keys.
The integration build owns the analysis registries imported in build_methodology().
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "web" / "data" / "methodology.json"
PIPELINE_ORDER = ["parse", "deterministic", "interpretive", "cluster", "dedup", "refute", "persist"]

STORY_ET = [
    "Apsakaleidja (aps + leidja) sai alguse lihtsast küsimusest: kas tehisintellekt suudab tuvastada seaduseelnõudes tehnilisi vigu enne, kui neist saavad seadused? Riigikogus menetletakse igal aastal sadu eelnõusid ning normitehnilised apsud — vale viide, vastuoluline üleminekusäte, kattuvad jõustumistähtajad — jõuavad vahel ka Riigi Teatajasse. Masin ei väsi ega kiirusta, seega lasime tal lugeda.",
    "See on projekti teine versioon. Esimene versioon (2026. aasta algusest) oli kiire katse: iga eelnõu kohta üks AI-päring, tekst kärbitud 30 000 märgini ja analüüsiloogika suletud. Katse õpetas kaks asja: mudel leiab tõelisi vigu — ja üksik mudelivastus ei ole usaldusväärne.",
    "Teine versioon on loodud täiesti uuesti kolme põhimõtte ümber. Skepsis enda suhtes: iga eelnõu analüüsitakse viis korda sõltumatult, avaldatakse vaid need leiud, mida kinnitab vähemalt kolm viiest analüüsist, ning eraldi skeptikusamm püüab iga leidu ümber lükata — ka ümberlükatud leiud jäävad lehel nähtavaks. Tekstipõhisus: leid, mis ei tsiteeri eelnõu sõna-sõnalt, jäetakse kõrvale. Avatus: kogu kood on GitHubis ning iga mudelivastus, vaheotsus ja analüüsi maksumus on avalikus andmebaasis — siit lehelt allalaaditav.",
    "Leiud on masina tähelepanekud, mitte õiguslik hinnang. Eesmärk ei ole asendada juristi ega Riigikogu Kantselei toimetajaid, vaid pakkuda neile — ja igale huvilisele — kiiret teist vaadet.",
]

STORY_EN = [
    "Apsakaleidja — Estonian for \"blunder-finder\" — began with a simple question: can AI "
    "find technical errors in draft legislation before the draft becomes law? The Riigikogu "
    "handles hundreds of bills a year, and drafting slips — a wrong cross-reference, a "
    "contradictory transition provision, overlapping entry-into-force dates — occasionally "
    "make it into the statute book. A machine does not tire or rush, so we let it read.",
    "This is the second version of the project. The first (early 2026) was a quick "
    "experiment: one AI query per bill, text truncated at 30,000 characters, and the "
    "analysis logic closed. The experiment taught us two things: the model finds real "
    "errors — and a single model response, on its own, cannot be trusted.",
    "Version two was rebuilt from scratch around three principles. Skepticism about "
    "itself: every bill is analysed five times independently, only findings confirmed by "
    "at least three of the five runs are published, and a separate skeptic pass tries to "
    "refute each finding — refuted findings stay visible on the page. Grounding: a finding "
    "that does not quote the bill verbatim is discarded. Openness: all the code is on "
    "GitHub, and every model response, intermediate decision and analysis cost sits in a "
    "public database — downloadable from this page.",
    "Findings are machine observations, not legal opinions. The goal is not to replace "
    "lawyers or the Riigikogu's drafting editors, but to offer them — and anyone "
    "interested — a fast second pair of eyes.",
]

LIMITATIONS_ET = [
    "Muutmisseaduste puhul analüüsitakse ainult eelnõu enda teksti ehk muudatusettepanekute sõnastust. Süsteem ei koosta muudetava seaduse tulevast tervikteksti ega võrdle eelnõud Riigi Teataja kehtiva redaktsiooniga — vead, mis ilmnevad alles muudatuse ja kehtiva seaduse koosmõjus, jäävad märkamata. (Täiesti uue seaduse eelnõu puhul on analüüsitav tekst ühtlasi kogu tulevane seadus.)",
    "Analüüsitakse ainult eelnõu põhiteksti — seletuskirja ei kaasata.",
    "Vanas .doc-vormingus ja pildipõhiseid PDF-e ei suudeta lugeda (tekst puudub).",
    "Deterministlikud kontrollid katavad mehaanilisi vigu; sisulisi hinnanguid annab keelemudel, mille leiud on tõenäosuslikud: mudel võib näha probleemi seal, kus seda tegelikult ei ole, ja jätta mõne vea märkamata. Avaldamiskünnis ja skeptikusamm vähendavad neid riske, kuid kumbagi ei kõrvalda täielikult.",
    "Korpus: seaduseelnõud (SE), mille menetluses on toimunud muudatusi alates 1. jaanuarist 2026.",
]

LIMITATIONS_EN = [
    "For amending acts, only the text of the bill itself — the wording of the amendment "
    "instructions — is analysed. The system does not construct the future consolidated text "
    "of the amended act and does not compare the bill against the current consolidated text "
    "in Riigi Teataja, so errors that only emerge from the interaction between the amendment "
    "and the current law go unnoticed. (For a bill proposing an entirely new act, the "
    "analysed text is the whole future act.)",
    "Only the main text of the bill is analysed — explanatory memoranda are not analysed.",
    "Old .doc files and image-based PDFs cannot be read because they do not contain extractable text.",
    "Deterministic checks cover mechanical errors; substantive assessments are made by a "
    "language model and its findings are probabilistic: the model can see a problem where "
    "there is none and miss a real one. The publication threshold and the skeptic pass "
    "reduce both risks but eliminate neither.",
    "Corpus: draft acts (SE) whose proceedings have changed since 1 January 2026.",
]

DATA_API = {
    "base": "https://xnwagfmsakedcilpauvx.supabase.co/rest/v1",
    "note_et": "Kõik analüüsiandmed on avalikult loetavad. Lisa päisesse apikey (avalik publishable-võti lehe lähtekoodis).",
    "note_en": "All analysis data is publicly readable. Send the publishable key in the apikey header.",
    "tables": [
        "bills",
        "bill_documents",
        "analyses",
        "analysis_samples",
        "findings",
        "pipeline_runs",
        "honte_rules",
        "eval_labels",
        "bill_index",
        "analysis_history",
    ],
}


def _registry_sequence(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return list(value.values())
    return list(value)


def _category_keys(categories: Any) -> list[str]:
    if isinstance(categories, Mapping):
        return [str(key) for key in categories.keys()]
    return [str(item) for item in categories]


def _label(labels: Any, key: str) -> str:
    if isinstance(labels, Mapping):
        return str(labels[key])
    for item in labels:
        if isinstance(item, Sequence) and not isinstance(item, str) and len(item) >= 2 and str(item[0]) == key:
            return str(item[1])
    raise KeyError(key)


def _check_to_dict(spec: Any) -> dict[str, Any]:
    return {
        "id": spec.id,
        "version": spec.version,
        "enabled": spec.enabled,
        "category": spec.category,
        "name_et": spec.name_et,
        "name_en": spec.name_en,
        "description_et": spec.description_et,
        "description_en": spec.description_en,
    }


def _pass_to_dict(spec: Any) -> dict[str, Any]:
    prompt = spec.prompt
    return {
        "id": spec.id,
        "version": spec.version,
        "enabled": spec.enabled,
        "kind": spec.kind,
        "name_et": spec.name_et,
        "name_en": spec.name_en,
        "description_et": spec.description_et,
        "description_en": spec.description_en,
        "prompt_sha": spec.prompt_sha(),
        "system_prompt": prompt.SYSTEM_PROMPT,
        "user_template": prompt.USER_TEMPLATE,
    }


def build_methodology() -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import config
    from analysis.checkers.deterministic import CHECKS
    from analysis.models import CATEGORIES, CATEGORIES_EN
    from analysis.passes import PASSES
    from reference.honte import CATEGORY_SECONDARY, CATEGORY_TO_RULE, citation, load_honte_rules

    # Imported as part of the registry contract; citation() is authoritative for
    # the emitted public label and the maps are kept live for integration drift.
    _ = (CATEGORY_TO_RULE, CATEGORY_SECONDARY)

    return {
        "engine": {
            "provider": config.LLM_PROVIDER,
            "model": config.active_model(),
            "sampling": {
                "samples": config.SC_SAMPLES,
                "min_agreement": config.SC_MIN_AGREEMENT,
                "temperature": config.SC_TEMPERATURE,
            },
        },
        "pipeline_order": PIPELINE_ORDER,
        "checks": [_check_to_dict(spec) for spec in _registry_sequence(CHECKS)],
        "passes": [_pass_to_dict(spec) for spec in _registry_sequence(PASSES)],
        "categories": [
            {
                "key": key,
                "label_et": _label(CATEGORIES, key),
                "label_en": _label(CATEGORIES_EN, key),
                "honte_citation": citation(key),
            }
            for key in _category_keys(CATEGORIES)
        ],
        "honte_rules": load_honte_rules(),
        "story_et": STORY_ET,
        "story_en": STORY_EN,
        "limitations_et": LIMITATIONS_ET,
        "limitations_en": LIMITATIONS_EN,
        "data_api": DATA_API,
    }


def write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def check_json(data: dict[str, Any], path: Path) -> int:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(data, tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.write("\n")

    expected = tmp_path.read_text(encoding="utf-8")
    actual = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp_path.unlink(missing_ok=True)

    if actual == expected:
        print(f"{path} is up to date")
        return 0

    print(f"{path} has drifted; run `python3 web/export_methodology.py --write`.", file=sys.stderr)
    diff = difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile=str(path),
        tofile="generated",
        lineterm="",
    )
    for i, line in enumerate(diff):
        if i >= 120:
            print("... diff truncated ...", file=sys.stderr)
            break
        print(line, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the generated methodology JSON")
    parser.add_argument("--check", action="store_true", help="compare the current JSON with generated output")
    parser.add_argument("--path", type=Path, default=DEFAULT_OUTPUT, help="target JSON path")
    args = parser.parse_args(argv)

    data = build_methodology()
    if args.check:
        return check_json(data, args.path)

    write_json(data, args.path)
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
