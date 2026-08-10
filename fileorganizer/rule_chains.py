"""Validated Hazel-style condition/action chains and planning decisions."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fileorganizer.config import _APP_DATA_DIR
from fileorganizer.path_safety import is_within, validate_storage_name


SCHEMA_VERSION = "1.0"
DEFAULT_RULES_FILE = os.path.join(_APP_DATA_DIR, "rule_chains.json")
MAX_CHAINS = 256
MAX_CONDITIONS = 32
MAX_ACTIONS = 32
MAX_NESTING_DEPTH = 8
MAX_TEXT_LENGTH = 2048

CONDITION_TYPES = frozenset({
    "extension",
    "filename_pattern",
    "file_size",
    "file_count",
    "llm_confidence",
    "has_metadata",
    "metadata_value",
})
CONDITION_OPERATORS = frozenset({
    "==",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "contains",
    "not_contains",
    "matches",
    "in",
    "not_in",
})
LOGICAL_OPERATORS = frozenset({"AND", "OR"})
ACTION_TYPES = frozenset({"move", "rename", "skip", "webhook"})


class RuleValidationError(ValueError):
    """Raised when a persisted or edited rule chain is malformed."""


def _bounded_text(value: Any, field_name: str, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise RuleValidationError(f"{field_name} must be a string")
    value = value.strip()
    if required and not value:
        raise RuleValidationError(f"{field_name} is required")
    if len(value) > MAX_TEXT_LENGTH:
        raise RuleValidationError(
            f"{field_name} exceeds the {MAX_TEXT_LENGTH}-character limit"
        )
    return value


@dataclass
class RuleCondition:
    """One comparison against the file/folder planning context."""

    type: str
    value: Any = None
    operator: str = "=="
    property: str | None = None

    def validate(self) -> None:
        if self.type not in CONDITION_TYPES:
            raise RuleValidationError(f"unknown condition type: {self.type!r}")
        if self.operator not in CONDITION_OPERATORS:
            raise RuleValidationError(f"unknown condition operator: {self.operator!r}")
        if self.property is not None:
            self.property = _bounded_text(self.property, "condition property") or None
        if self.type in {"metadata_value", "has_metadata"} and not self.property:
            raise RuleValidationError(f"{self.type} requires a metadata property")
        if isinstance(self.value, str):
            self.value = _bounded_text(self.value, "condition value")
        if self.operator == "matches":
            try:
                re.compile(str(self.value))
            except re.error as exc:
                raise RuleValidationError(f"invalid condition regular expression: {exc}") from exc
        if self.type in {"file_size", "file_count", "llm_confidence"}:
            try:
                int(self.value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise RuleValidationError(f"{self.type} requires an integer value") from exc

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "value": self.value,
            "operator": self.operator,
        }
        if self.property:
            data["property"] = self.property
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleCondition:
        if not isinstance(data, dict):
            raise RuleValidationError("condition must be an object")
        condition = cls(
            type=_bounded_text(data.get("type"), "condition type", required=True),
            value=data.get("value"),
            operator=_bounded_text(
                data.get("operator", "=="), "condition operator", required=True
            ),
            property=data.get("property"),
        )
        condition.validate()
        return condition

    def evaluate(self, context: dict[str, Any]) -> bool:
        try:
            actual: Any
            expected: Any
            if self.type == "extension":
                actual = str(context.get("extension", "")).lower().lstrip(".")
                expected = str(self.value).lower().lstrip(".")
            elif self.type == "filename_pattern":
                actual = str(context.get("filename", ""))
                expected = self.value
            elif self.type in {"file_size", "file_count", "llm_confidence"}:
                actual = int(context.get(self.type, 0))
                expected = int(self.value)
            elif self.type == "metadata_value":
                metadata = context.get("metadata", {})
                if not isinstance(metadata, dict) or self.property not in metadata:
                    return False
                actual = metadata[self.property]
                expected = self.value
            elif self.type == "has_metadata":
                metadata = context.get("metadata", {})
                return isinstance(metadata, dict) and self.property in metadata
            else:
                return False
            return self._compare(actual, expected, self.operator)
        except (TypeError, ValueError, OverflowError, re.error):
            return False

    @staticmethod
    def _compare(actual: Any, expected: Any, operator: str) -> bool:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
        if operator == "contains":
            return str(expected).casefold() in str(actual).casefold()
        if operator == "not_contains":
            return str(expected).casefold() not in str(actual).casefold()
        if operator == "matches":
            return bool(re.search(str(expected), str(actual), re.IGNORECASE))
        if operator == "in":
            return actual in expected if isinstance(expected, (list, tuple)) else False
        if operator == "not_in":
            return actual not in expected if isinstance(expected, (list, tuple)) else True
        return False


@dataclass
class RuleAction:
    """One action produced when its containing chain matches."""

    type: str
    destination: str | None = None
    template: str | None = None
    url: str | None = None
    method: str = "POST"

    def validate(self) -> None:
        if self.type not in ACTION_TYPES:
            raise RuleValidationError(f"unknown action type: {self.type!r}")
        if self.type == "move":
            self.destination = _bounded_text(
                self.destination, "move destination", required=True
            )
        elif self.type == "rename":
            self.template = _bounded_text(self.template, "rename template", required=True)
        elif self.type == "webhook":
            self.url = _bounded_text(self.url, "webhook URL", required=True)
            if not self.url.lower().startswith("https://"):
                raise RuleValidationError("webhook URL must use HTTPS")
            self.method = _bounded_text(self.method, "webhook method", required=True).upper()
            if self.method != "POST":
                raise RuleValidationError("only POST webhooks are supported")

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleAction:
        if not isinstance(data, dict):
            raise RuleValidationError("action must be an object")
        action = cls(
            type=_bounded_text(data.get("type"), "action type", required=True),
            destination=data.get("destination"),
            template=data.get("template"),
            url=data.get("url"),
            method=data.get("method", "POST"),
        )
        action.validate()
        return action

    @staticmethod
    def _substitute_variables(template: str, context: dict[str, Any]) -> str:
        now = datetime.now()
        replacements = {
            "$HOME": os.path.expanduser("~"),
            "$DEST_ROOT": str(context.get("dest_root", "")),
            "$CATEGORY": str(context.get("category", "Unknown")),
            "$NAME": str(context.get("folder_name", "unnamed")),
            "$YEAR": str(now.year),
            "$MONTH": f"{now.month:02d}",
            "$DAY": f"{now.day:02d}",
        }
        result = template
        for token, value in replacements.items():
            result = result.replace(token, value)
        metadata = context.get("metadata", {})
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if isinstance(key, str) and isinstance(value, (str, int, float)):
                    result = result.replace("{" + key + "}", str(value))
        return result

    def execute(self, folder_path: str, context: dict[str, Any]) -> tuple[bool, str]:
        """Compatibility mutation API; plan-driven callers should use ``plan``."""
        try:
            if self.type == "skip":
                return True, "Skipped"
            if self.type == "webhook":
                return False, "Webhook actions are deferred and never run during file planning"
            if self.type == "rename":
                if not self.template:
                    return False, "No template specified"
                new_name = validate_storage_name(
                    self._substitute_variables(self.template, context)
                )
                new_path = os.path.join(os.path.dirname(folder_path), new_name)
                if os.path.lexists(new_path):
                    return False, f"Destination already exists: {new_path}"
                os.rename(folder_path, new_path)
                return True, f"Renamed to {new_name}"
            if self.type == "move":
                if not self.destination:
                    return False, "No destination specified"
                destination = os.path.abspath(
                    self._substitute_variables(self.destination, context)
                )
                approved_root = context.get("dest_root")
                if approved_root and not is_within(destination, str(approved_root)):
                    return False, "Move destination escapes the approved destination root"
                os.makedirs(destination, exist_ok=True)
                new_path = os.path.join(destination, os.path.basename(folder_path))
                if os.path.lexists(new_path):
                    return False, f"Destination already exists: {new_path}"
                shutil.move(folder_path, new_path)
                return True, f"Moved to {new_path}"
            return False, f"Unknown action type: {self.type}"
        except Exception as exc:
            return False, f"Action failed: {exc}"


@dataclass
class RuleDecision:
    """Pure planning result consumed by organize_run's move-plan builder."""

    matched_rules: list[str] = field(default_factory=list)
    skip: bool = False
    destination: str | None = None
    rename: str | None = None
    deferred_actions: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class RuleChain:
    """Conditions combined by AND/OR, ordered actions, then nested chains."""

    conditions: list[RuleCondition] = field(default_factory=list)
    logical_operator: str = "AND"
    actions: list[RuleAction] = field(default_factory=list)
    then_chains: list[RuleChain] = field(default_factory=list)
    name: str | None = None
    enabled: bool = True

    def validate(self, depth: int = 0) -> None:
        if depth > MAX_NESTING_DEPTH:
            raise RuleValidationError(
                f"rule nesting exceeds {MAX_NESTING_DEPTH} levels"
            )
        if self.name is not None:
            self.name = _bounded_text(self.name, "rule name") or None
        if self.logical_operator not in LOGICAL_OPERATORS:
            raise RuleValidationError(
                f"unknown logical operator: {self.logical_operator!r}"
            )
        if len(self.conditions) > MAX_CONDITIONS:
            raise RuleValidationError(f"a rule may have at most {MAX_CONDITIONS} conditions")
        if len(self.actions) > MAX_ACTIONS:
            raise RuleValidationError(f"a rule may have at most {MAX_ACTIONS} actions")
        if len(self.then_chains) > MAX_CHAINS:
            raise RuleValidationError(f"a rule may have at most {MAX_CHAINS} THEN chains")
        for condition in self.conditions:
            condition.validate()
        for action in self.actions:
            action.validate()
        for child in self.then_chains:
            child.validate(depth + 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "logical_operator": self.logical_operator,
            "actions": [action.to_dict() for action in self.actions],
            "then_chains": [chain.to_dict() for chain in self.then_chains],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, depth: int = 0) -> RuleChain:
        if not isinstance(data, dict):
            raise RuleValidationError("rule chain must be an object")
        if depth > MAX_NESTING_DEPTH:
            raise RuleValidationError(
                f"rule nesting exceeds {MAX_NESTING_DEPTH} levels"
            )
        raw_conditions = data.get("conditions", [])
        raw_actions = data.get("actions", [])
        raw_children = data.get("then_chains", [])
        if not all(isinstance(value, list) for value in (
            raw_conditions, raw_actions, raw_children
        )):
            raise RuleValidationError("conditions, actions, and then_chains must be arrays")
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise RuleValidationError("rule enabled must be true or false")
        chain = cls(
            name=data.get("name"),
            enabled=enabled,
            conditions=[RuleCondition.from_dict(value) for value in raw_conditions],
            logical_operator=_bounded_text(
                data.get("logical_operator", "AND"),
                "logical operator",
                required=True,
            ).upper(),
            actions=[RuleAction.from_dict(value) for value in raw_actions],
            then_chains=[
                cls.from_dict(value, depth=depth + 1) for value in raw_children
            ],
        )
        chain.validate(depth)
        return chain

    def evaluate(self, context: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if not self.conditions:
            return True
        results = [condition.evaluate(context) for condition in self.conditions]
        return all(results) if self.logical_operator == "AND" else any(results)

    def plan(self, context: dict[str, Any], decision: RuleDecision | None = None) -> RuleDecision:
        decision = decision or RuleDecision()
        if not self.evaluate(context):
            return decision
        rule_name = self.name or "unnamed"
        decision.matched_rules.append(rule_name)
        for action in self.actions:
            if action.type == "skip":
                decision.skip = True
                decision.messages.append(f"{rule_name}: skip")
                break
            if action.type == "move" and action.destination:
                decision.destination = action._substitute_variables(
                    action.destination, context
                )
                decision.messages.append(
                    f"{rule_name}: move to {decision.destination}"
                )
            elif action.type == "rename" and action.template:
                decision.rename = action._substitute_variables(action.template, context)
                context = {**context, "folder_name": decision.rename}
                decision.messages.append(f"{rule_name}: rename to {decision.rename}")
            elif action.type == "webhook":
                decision.deferred_actions.append(action.to_dict())
                decision.messages.append(f"{rule_name}: webhook deferred")
        if not decision.skip:
            for child in self.then_chains:
                child.plan(context, decision)
                if decision.skip:
                    break
        return decision

    def execute(
        self,
        folder_path: str,
        context: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        if not self.enabled:
            return False, ["Chain disabled"]
        if not self.evaluate(context):
            return False, ["Conditions not met"]
        any_success = False
        messages: list[str] = []
        for action in self.actions:
            success, message = action.execute(folder_path, context)
            messages.append(message)
            any_success = any_success or success
        for child in self.then_chains:
            success, child_messages = child.execute(folder_path, context)
            messages.extend(child_messages)
            any_success = any_success or success
        return any_success, messages


class RuleChainManager:
    """Load, validate, save, and evaluate a bounded ordered rule set."""

    def __init__(self, rules_file: str | None = None) -> None:
        self.rules_file = rules_file or DEFAULT_RULES_FILE
        self.chains: list[RuleChain] = []
        self.load_error = ""
        self._load_chains()

    @staticmethod
    def _validate_collection(chains: list[RuleChain]) -> None:
        if len(chains) > MAX_CHAINS:
            raise RuleValidationError(f"at most {MAX_CHAINS} root rules are allowed")
        names: set[str] = set()
        for chain in chains:
            chain.validate()
            if chain.name:
                key = chain.name.casefold()
                if key in names:
                    raise RuleValidationError(f"duplicate rule name: {chain.name!r}")
                names.add(key)

    def _load_chains(self) -> None:
        path = Path(self.rules_file)
        if not path.is_file():
            self.chains = []
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                raw_chains = data
            elif isinstance(data, dict) and data.get("version", SCHEMA_VERSION) == SCHEMA_VERSION:
                raw_chains = data.get("chains", [])
            else:
                raise RuleValidationError("unsupported rule-chain schema")
            if not isinstance(raw_chains, list):
                raise RuleValidationError("rule chains must be an array")
            chains = [RuleChain.from_dict(value) for value in raw_chains]
            self._validate_collection(chains)
            self.chains = chains
        except (OSError, json.JSONDecodeError, RuleValidationError) as exc:
            self.chains = []
            self.load_error = str(exc)

    def _save_chains(self) -> None:
        self._validate_collection(self.chains)
        path = Path(self.rules_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "chains": [chain.to_dict() for chain in self.chains],
        }
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temp_name = stream.name
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        except OSError as exc:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            raise RuleValidationError(f"could not save rule chains: {exc}") from exc

    def replace_chains(self, chains: list[RuleChain]) -> None:
        self._validate_collection(chains)
        self.chains = chains
        self._save_chains()

    def add_chain(self, chain: RuleChain) -> None:
        self.replace_chains([*self.chains, chain])

    def remove_chain(self, name: str) -> bool:
        updated = [chain for chain in self.chains if chain.name != name]
        if len(updated) == len(self.chains):
            return False
        self.replace_chains(updated)
        return True

    def plan(self, context: dict[str, Any]) -> RuleDecision:
        decision = RuleDecision()
        for chain in self.chains:
            chain.plan(dict(context), decision)
            if decision.skip:
                break
        return decision

    def evaluate_and_execute(
        self,
        folder_path: str,
        context: dict[str, Any],
    ) -> list[tuple[str, bool, list[str]]]:
        results: list[tuple[str, bool, list[str]]] = []
        for chain in self.chains:
            if chain.evaluate(context):
                success, messages = chain.execute(folder_path, context)
                results.append((chain.name or "unnamed", success, messages))
        return results
