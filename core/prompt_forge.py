# Offline tag selection and assembly for Prompt Forge.

import random
from pathlib import Path

from .logger import log

_LOG_PREFIX = "DanbooruPromptForge"

DATA_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "prompts" / "tag_lists"
)

DEFAULT_EXCLUDE_CATEGORIES = (
    "artist, character_name, copyright, meta, speech_and_text, "
    "metadata_and_attribution, intentional_design_exposure, "
    "content_censorship_methods"
)
DEFAULT_TAGLISTS_MUST_INCLUDE = "1girl"

FEATURE_OPTIONS = (
    "general",
    "questionable",
    "sensitive",
    "explicit",
    "replace_underscores",
    "ignore_missing",
    "categories",
)
DEFAULT_FEATURES = ["general", "replace_underscores"]

CONTENT_POOL_FILES = (
    ("general", "taglists-general.txt"),
    ("questionable", "taglists-questionable.txt"),
    ("sensitive", "taglists-sensitive.txt"),
    ("explicit", "taglists-explicit.txt"),
)


def _normalize_tags(tag_string: str) -> list[str]:
    tag_string = tag_string.replace("\r\n", "\n").replace("\n", ",")

    while "  " in tag_string:
        tag_string = tag_string.replace("  ", " ")
    while ",," in tag_string:
        tag_string = tag_string.replace(",,", ",")

    return [
        tag.strip().replace(" ", "_")
        for tag in tag_string.replace(", ", ",").split(",")
        if tag.strip()
    ]


def _normalize_features(value: str | list[str]) -> list[str]:
    raw_values = value.split(",") if isinstance(value, str) else value
    return list(
        dict.fromkeys(
            feature.strip()
            for feature in raw_values
            if isinstance(feature, str) and feature.strip() in FEATURE_OPTIONS
        )
    )


def _rating_line_tags(taglist: str) -> list[str]:
    fields = taglist.split(",")
    if len(fields) < 3:
        return []
    return _normalize_tags(",".join(fields[2:]))


def _load_categories(data_directory: Path) -> list[str]:
    categories_file = data_directory / "categories.txt"
    if categories_file.exists():
        try:
            return sorted(
                line.strip()
                for line in categories_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        except OSError:
            pass

    categories: set[str] = set()
    categorized_tags_file = data_directory / "categorized_tags.txt"
    try:
        with categorized_tags_file.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if line.startswith("[") and "] " in line:
                    categories.add(line[1 : line.index("]")])
    except OSError:
        pass
    return sorted(categories)


def _load_available_tags(filepath: Path) -> set[str]:
    available_tags: set[str] = set()

    try:
        with filepath.open("r", encoding="utf-8") as handle:
            for raw_taglist in handle:
                taglist = raw_taglist.strip()
                if taglist:
                    available_tags.update(_rating_line_tags(taglist))
    except FileNotFoundError as exc:
        raise ValueError(f"Taglist data file not found at {filepath}") from exc

    return available_tags


def _load_matching_taglists(
    filepath: Path,
    required_tags: set[str],
) -> list[tuple[str, str]]:
    valid_taglists: list[tuple[str, str]] = []

    try:
        with filepath.open("r", encoding="utf-8") as handle:
            for raw_taglist in handle:
                taglist = raw_taglist.strip()
                if not taglist:
                    continue

                taglist_tags = frozenset(_rating_line_tags(taglist))
                if required_tags and not required_tags.issubset(taglist_tags):
                    continue

                valid_taglists.append((filepath.name, taglist))
    except FileNotFoundError as exc:
        raise ValueError(f"Taglist data file not found at {filepath}") from exc

    return valid_taglists


def build_prompt(
    seed: int,
    features: str | list[str],
    prefix: str = "",
    taglists_must_include: str = DEFAULT_TAGLISTS_MUST_INCLUDE,
    custom_prompt: str = "",
    exclude_tag_categories: str = DEFAULT_EXCLUDE_CATEGORIES,
    *,
    data_directory: Path | None = None,
) -> str:
    data_directory = DATA_DIRECTORY if data_directory is None else data_directory
    if not data_directory.is_dir():
        raise ValueError(
            f"Danbooru Prompt Forge data directory not found at {data_directory}"
        )

    enabled_features = set(_normalize_features(features))
    allowed_tags: list[str] = []
    if "categories" in enabled_features:
        categorized_tags_file = data_directory / "categorized_tags.txt"
        if not categorized_tags_file.is_file():
            raise ValueError(
                f"Categorized tags file not found at {categorized_tags_file}"
            )

        all_categories = _load_categories(data_directory)
        excluded_categories = _normalize_tags(exclude_tag_categories)
        invalid_categories = [
            category
            for category in excluded_categories
            if category not in all_categories
        ]
        if invalid_categories:
            raise ValueError(
                f"Error: Invalid category names: {', '.join(invalid_categories)}. "
                f"Valid categories: {', '.join(all_categories)}"
            )

        enabled_categories = {
            category: category not in excluded_categories
            for category in all_categories
        }
        with categorized_tags_file.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split("] ", 1)
                if len(parts) != 2:
                    continue
                category = parts[0][1:]
                tag = parts[1]
                if enabled_categories.get(category):
                    allowed_tags.append(tag)

    required_tags = _normalize_tags(taglists_must_include)
    required_tag_set = set(required_tags)
    enabled_pool_files = [
        data_directory / filename
        for rating, filename in CONTENT_POOL_FILES
        if rating in enabled_features
    ]

    effective_required_tags = required_tag_set
    if "ignore_missing" in enabled_features and enabled_pool_files:
        available_tags: set[str] = set()
        for filepath in enabled_pool_files:
            available_tags.update(_load_available_tags(filepath))
        missing_required_tags = sorted(required_tag_set - available_tags)
        if missing_required_tags:
            log.warning(
                _LOG_PREFIX,
                "Ignoring required tags not found in enabled rating pools: "
                + ", ".join(missing_required_tags),
            )
        effective_required_tags = required_tag_set & available_tags

    valid_taglists: list[tuple[str, str]] = []
    for filepath in enabled_pool_files:
        valid_taglists.extend(
            _load_matching_taglists(filepath, effective_required_tags)
        )

    if not valid_taglists:
        raise ValueError("No tags available - no matching taglists found")

    rng = random.Random(seed)
    rng.shuffle(valid_taglists)
    _, selected_taglist = valid_taglists[seed % len(valid_taglists)]
    individual_tags = _rating_line_tags(selected_taglist)
    if "categories" in enabled_features:
        allowed_tag_order = {
            tag: index for index, tag in enumerate(allowed_tags)
        }
        filtered_tags = [
            tag for tag in individual_tags if tag in allowed_tag_order
        ]
        filtered_tags.sort(
            key=lambda tag: allowed_tag_order[tag]
        )
    else:
        filtered_tags = individual_tags

    assembled_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in [
        *_normalize_tags(prefix),
        *required_tags,
        *_normalize_tags(custom_prompt),
        *filtered_tags,
    ]:
        if tag in seen_tags:
            continue
        seen_tags.add(tag)
        assembled_tags.append(tag)

    final_prompt = ", ".join(assembled_tags)
    if "replace_underscores" in enabled_features:
        final_prompt = final_prompt.replace("_", " ")

    return final_prompt
