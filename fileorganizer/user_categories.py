"""User-taught category storage and optional SetFit training."""
from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from fileorganizer.config import (
    _APP_DATA_DIR,
    _USER_CATEGORIES_FILE,
    _USER_CATEGORY_MODELS_DIR,
)
from fileorganizer.naming import _normalize


DEFAULT_BASE_MODEL = "minishlab/potion-base-32M"
MIN_EXAMPLES = 8
SCHEMA_VERSION = 1
MAX_EXAMPLE_FILES = 80
MAX_NEGATIVE_TEXTS = 96

_STOP_WORDS = {
    "and", "for", "the", "with", "from", "this", "that", "into", "your",
    "pack", "bundle", "asset", "assets", "template", "templates", "file",
    "files", "folder", "folders", "download", "downloads", "preview",
    "readme", "license", "version", "final", "copy", "project",
}
_MODEL_CACHE: dict[str, Any] = {}


class UserCategoryError(ValueError):
    """Raised for invalid taught-category input."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        out.append(text)
        seen.add(key)
    return out


def _safe_read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _invalidate_category_index() -> None:
    try:
        from fileorganizer.categories import _CategoryIndex
        _CategoryIndex.invalidate()
    except Exception:
        pass


def _coerce_keywords(name: str, keywords: Iterable[str] | None) -> list[str]:
    values = _dedupe(k.lower() for k in (keywords or []))
    if name and name.lower() not in {k.casefold() for k in values}:
        values.insert(0, name.lower())
    return values or ([name.lower()] if name else [])


def validate_examples(
    examples: Iterable[str | os.PathLike[str]],
    minimum: int = MIN_EXAMPLES,
    *,
    require_exists: bool = True,
) -> list[str]:
    """Return de-duplicated example paths or raise UserCategoryError."""
    paths = _dedupe(os.fspath(p) for p in examples)
    if len(paths) < minimum:
        raise UserCategoryError(f"At least {minimum} examples are required.")
    if require_exists:
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            preview = ", ".join(missing[:3])
            more = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
            raise UserCategoryError(f"Example path does not exist: {preview}{more}")
    return paths


def _path_words(path: Path) -> list[str]:
    parts = [path.stem or path.name]
    parent_parts = [p for p in path.parts[-4:-1] if p and p not in (os.sep,)]
    parts.extend(parent_parts)
    if path.suffix:
        parts.append(path.suffix.lstrip("."))
    return parts


def _clean_text(text: str) -> str:
    text = re.sub(r"[_./\\|()[\]{}:+]+", " ", text)
    text = re.sub(r"\b\d{5,}\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_example_text(example_path: str | os.PathLike[str]) -> str:
    """Build lightweight training text from a file or folder path."""
    path = Path(example_path)
    parts: list[str] = _path_words(path)
    if path.is_dir():
        root_depth = len(path.parts)
        seen_files = 0
        try:
            for root, dirs, files in os.walk(path):
                rel_depth = max(0, len(Path(root).parts) - root_depth)
                if rel_depth > 2:
                    dirs.clear()
                    continue
                parts.extend(d for d in dirs[:20] if d)
                for filename in files[:40]:
                    if seen_files >= MAX_EXAMPLE_FILES:
                        break
                    fpath = Path(filename)
                    parts.append(fpath.stem)
                    if fpath.suffix:
                        parts.append(fpath.suffix.lstrip("."))
                    seen_files += 1
                if seen_files >= MAX_EXAMPLE_FILES:
                    break
        except (OSError, PermissionError):
            pass
    return _clean_text(" ".join(parts))


def build_example_rows(examples: Iterable[str | os.PathLike[str]]) -> list[dict[str, str]]:
    rows = []
    for path in examples:
        text = extract_example_text(path)
        rows.append({"path": os.fspath(path), "text": text})
    return rows


def derive_keywords(
    name: str,
    example_rows: Iterable[dict[str, str]],
    *,
    explicit_keywords: Iterable[str] | None = None,
    max_keywords: int = 18,
) -> list[str]:
    """Derive stable keyword hints from taught examples."""
    keywords = _coerce_keywords(name, explicit_keywords)
    counter: Counter[str] = Counter()
    for row in example_rows:
        norm = _normalize(row.get("text", ""))
        for token in norm.split():
            if len(token) < 3 or token.isdigit() or token in _STOP_WORDS:
                continue
            counter[token] += 1
    for token, _count in counter.most_common(max_keywords):
        if token.casefold() not in {k.casefold() for k in keywords}:
            keywords.append(token)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _normalize_example(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        return {"path": value, "text": extract_example_text(value)}
    if isinstance(value, dict):
        path = str(value.get("path", "")).strip()
        if not path:
            return None
        text = str(value.get("text", "")).strip() or extract_example_text(path)
        return {"path": path, "text": text}
    return None


def normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    name = str(record.get("name", "")).strip()
    if not name:
        return None
    examples = []
    for value in record.get("examples", []):
        row = _normalize_example(value)
        if row:
            examples.append(row)
    training = dict(record.get("training") or {})
    keywords = _coerce_keywords(name, record.get("keywords") or [])
    status = str(record.get("status") or training.get("status") or "keyword_only")
    return {
        "name": name,
        "keywords": keywords,
        "examples": examples,
        "status": status,
        "created_at": str(record.get("created_at") or _now_iso()),
        "updated_at": str(record.get("updated_at") or _now_iso()),
        "training": {
            "base_model": str(training.get("base_model") or DEFAULT_BASE_MODEL),
            "model_dir": str(training.get("model_dir") or ""),
            "trained_at": training.get("trained_at"),
            "error": str(training.get("error") or ""),
        },
    }


def load_user_category_records(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Load taught categories from user_categories.json."""
    file_path = os.fspath(path or _USER_CATEGORIES_FILE)
    data = _safe_read_json(file_path)
    if isinstance(data, dict):
        raw_records = data.get("categories", [])
    elif isinstance(data, list):
        raw_records = data
    else:
        raw_records = []
    records = []
    for raw in raw_records:
        if isinstance(raw, dict):
            rec = normalize_record(raw)
            if rec:
                records.append(rec)
    return records


def save_user_category_records(
    records: Iterable[dict[str, Any]],
    path: str | os.PathLike[str] | None = None,
) -> None:
    file_path = os.fspath(path or _USER_CATEGORIES_FILE)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    normalized = [r for r in (normalize_record(dict(rec)) for rec in records) if r]
    payload = {"schema_version": SCHEMA_VERSION, "categories": normalized}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    _invalidate_category_index()


def load_user_categories(path: str | os.PathLike[str] | None = None) -> list[tuple[str, list[str]]]:
    return [(r["name"], list(r["keywords"])) for r in load_user_category_records(path)]


def upsert_user_category(
    record: dict[str, Any],
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_record(record)
    if not normalized:
        raise UserCategoryError("Category name is required.")
    records = load_user_category_records(path)
    key = normalized["name"].casefold()
    replaced = False
    for idx, existing in enumerate(records):
        if existing["name"].casefold() == key:
            if not normalized.get("created_at") and existing.get("created_at"):
                normalized["created_at"] = existing["created_at"]
            records[idx] = normalized
            replaced = True
            break
    if not replaced:
        records.append(normalized)
    save_user_category_records(records, path)
    return normalized


def remove_user_category(name: str, path: str | os.PathLike[str] | None = None) -> bool:
    records = load_user_category_records(path)
    key = name.strip().casefold()
    kept = [r for r in records if r["name"].casefold() != key]
    if len(kept) == len(records):
        return False
    save_user_category_records(kept, path)
    return True


def _negative_training_texts(category_name: str, limit: int = MAX_NEGATIVE_TEXTS) -> list[str]:
    try:
        from fileorganizer.categories import BUILTIN_CATEGORIES, load_custom_categories
    except Exception:
        return ["general design asset", "miscellaneous template", "other file"]
    rows: list[str] = []
    key = category_name.casefold()
    for name, keywords in list(BUILTIN_CATEGORIES) + load_custom_categories():
        if name.casefold() == key:
            continue
        rows.append(_clean_text(" ".join([name, *list(keywords)[:6]])))
        if len(rows) >= limit:
            break
    return rows


def setfit_available() -> tuple[bool, str]:
    try:
        import datasets  # noqa: F401
        import setfit  # noqa: F401
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _load_setfit_stack():
    from datasets import Dataset
    from setfit import SetFitModel, SetFitTrainer
    try:
        from setfit import TrainingArguments
    except Exception:
        TrainingArguments = None
    return Dataset, SetFitModel, SetFitTrainer, TrainingArguments


def _train_setfit_model(
    record: dict[str, Any],
    *,
    output_root: str | os.PathLike[str] | None = None,
    model_factory: Callable[[str], Any] | None = None,
    trainer_factory: Callable[..., Any] | None = None,
    dataset_factory: Callable[[dict[str, list[Any]]], Any] | None = None,
) -> dict[str, Any]:
    Dataset, SetFitModel, SetFitTrainer, TrainingArguments = _load_setfit_stack()
    name = record["name"]
    positive_texts = [row["text"] for row in record.get("examples", []) if row.get("text")]
    negative_texts = _negative_training_texts(name, max(len(positive_texts) * 4, 24))
    if not positive_texts or not negative_texts:
        raise UserCategoryError("Training requires positive and negative examples.")

    texts = positive_texts + negative_texts
    labels = [name] * len(positive_texts) + ["__not_category__"] * len(negative_texts)
    dataset_payload = {"text": texts, "label": labels}
    dataset = dataset_factory(dataset_payload) if dataset_factory else Dataset.from_dict(dataset_payload)

    base_model = record["training"].get("base_model") or DEFAULT_BASE_MODEL
    if model_factory:
        model = model_factory(base_model)
    else:
        model = SetFitModel.from_pretrained(base_model)

    if trainer_factory:
        trainer = trainer_factory(model=model, train_dataset=dataset)
    else:
        trainer_kwargs = {
            "model": model,
            "train_dataset": dataset,
            "column_mapping": {"text": "text", "label": "label"},
        }
        if TrainingArguments is not None:
            try:
                args = TrainingArguments(
                    batch_size=min(8, max(1, len(texts))),
                    num_epochs=1,
                    max_steps=min(80, max(16, len(texts) * 2)),
                )
                trainer_kwargs["args"] = args
            except TypeError:
                pass
        try:
            trainer = SetFitTrainer(**trainer_kwargs)
        except TypeError:
            trainer_kwargs.pop("column_mapping", None)
            trainer = SetFitTrainer(**trainer_kwargs)

    trainer.train()
    model_root = os.fspath(output_root or _USER_CATEGORY_MODELS_DIR)
    model_dir = os.path.join(model_root, _slugify(name))
    if os.path.exists(model_dir):
        shutil.rmtree(model_dir)
    os.makedirs(os.path.dirname(model_dir), exist_ok=True)
    if hasattr(model, "save_pretrained"):
        model.save_pretrained(model_dir)
    else:
        os.makedirs(model_dir, exist_ok=True)

    trained = dict(record)
    trained["status"] = "trained"
    trained["training"] = dict(record["training"])
    trained["training"].update({
        "base_model": base_model,
        "model_dir": model_dir,
        "trained_at": _now_iso(),
        "error": "",
    })
    return trained


def teach_category(
    name: str,
    examples: Iterable[str | os.PathLike[str]],
    *,
    keywords: Iterable[str] | None = None,
    train: bool = True,
    require_exists: bool = True,
    path: str | os.PathLike[str] | None = None,
    base_model: str = DEFAULT_BASE_MODEL,
    output_root: str | os.PathLike[str] | None = None,
    model_factory: Callable[[str], Any] | None = None,
    trainer_factory: Callable[..., Any] | None = None,
    dataset_factory: Callable[[dict[str, list[Any]]], Any] | None = None,
) -> dict[str, Any]:
    """Create or replace a user-taught category.

    If SetFit is unavailable or training fails, the category is still saved as
    keyword_only so it immediately participates in taxonomy matching.
    """
    cat_name = name.strip()
    if not cat_name:
        raise UserCategoryError("Category name is required.")
    paths = validate_examples(examples, require_exists=require_exists)
    rows = build_example_rows(paths)
    now = _now_iso()
    record = {
        "name": cat_name,
        "keywords": derive_keywords(cat_name, rows, explicit_keywords=keywords),
        "examples": rows,
        "status": "keyword_only",
        "created_at": now,
        "updated_at": now,
        "training": {
            "base_model": base_model,
            "model_dir": "",
            "trained_at": None,
            "error": "",
        },
    }

    if train:
        try:
            record = _train_setfit_model(
                record,
                output_root=output_root,
                model_factory=model_factory,
                trainer_factory=trainer_factory,
                dataset_factory=dataset_factory,
            )
        except Exception as exc:
            record["status"] = "keyword_only"
            record["training"]["error"] = str(exc)

    return upsert_user_category(record, path)


def _match_keywords(text: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    norm = _normalize(text)
    tokens = set(norm.split())
    best: dict[str, Any] | None = None
    for record in records:
        best_score = 0.0
        best_kw = ""
        for keyword in record.get("keywords", []):
            kw_norm = _normalize(keyword)
            if not kw_norm:
                continue
            if norm == kw_norm:
                score = 100.0
            elif len(kw_norm) > 4 and kw_norm in norm:
                score = min(98.0, 62.0 + len(kw_norm))
            else:
                kw_tokens = {t for t in kw_norm.split() if len(t) > 2}
                if kw_tokens:
                    overlap = kw_tokens & tokens
                    score = (len(overlap) / len(kw_tokens)) * 88.0 if overlap else 0.0
                else:
                    score = 0.0
            if score > best_score:
                best_score = score
                best_kw = keyword
        if best_score >= 65 and (best is None or best_score > best["confidence"]):
            best = {
                "category": record["name"],
                "confidence": min(96.0, best_score),
                "method": "user_category",
                "detail": f"user_keyword:{best_kw}",
            }
    return best


def _classify_with_setfit(text: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    trained_records = [
        r for r in records
        if r.get("status") == "trained" and r.get("training", {}).get("model_dir")
    ]
    if not trained_records:
        return None
    try:
        _Dataset, SetFitModel, _Trainer, _Args = _load_setfit_stack()
    except Exception:
        return None

    best: dict[str, Any] | None = None
    for record in trained_records:
        model_dir = record["training"]["model_dir"]
        if not os.path.isdir(model_dir):
            continue
        try:
            model = _MODEL_CACHE.get(model_dir)
            if model is None:
                model = SetFitModel.from_pretrained(model_dir)
                _MODEL_CACHE[model_dir] = model
            predicted = model.predict([text])[0]
            if str(predicted) != record["name"]:
                continue
            confidence = 86.0
            if hasattr(model, "predict_proba"):
                try:
                    probs = model.predict_proba([text])[0]
                    confidence = max(float(p) for p in probs) * 100.0
                except Exception:
                    pass
            if confidence >= 65 and (best is None or confidence > best["confidence"]):
                best = {
                    "category": record["name"],
                    "confidence": min(98.0, confidence),
                    "method": "user_category",
                    "detail": f"user_setfit:{Path(model_dir).name}",
                }
        except Exception:
            continue
    return best


def classify_user_category(
    folder_name: str,
    *,
    scan: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a taught-category hit for a folder name/scan, if one is strong."""
    loaded = records if records is not None else load_user_category_records()
    if not loaded:
        return None
    text_parts = [folder_name]
    if scan:
        text_parts.extend(scan.get("all_filenames_clean") or [])
    text = _clean_text(" ".join(str(p) for p in text_parts if p))
    if not text:
        return None
    model_hit = _classify_with_setfit(text, loaded)
    if model_hit:
        return model_hit
    return _match_keywords(text, loaded)
