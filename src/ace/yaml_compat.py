from __future__ import annotations

import json
import re
from typing import Any

try:  # Optional: full YAML support when installed.
    import yaml as _yaml
except ImportError:
    _yaml = None


class _NoAliasDumper(_yaml.SafeDumper if _yaml else object):
    if _yaml:
        def ignore_aliases(self, data):
            return True


def _scalar_dump(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return "''"
    if "\n" in text:
        return "|"
    # Quote anything that could be parsed as syntax or another scalar type.
    if (
        text.strip() != text
        or re.search(r"[:#\[\]{}&,*!?|>'\"%@`]", text)
        or text.lower() in {"true", "false", "null", "none", "yes", "no"}
        or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    ):
        return json.dumps(text, ensure_ascii=False)
    return text


def _mini_dump(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            key_text = str(key)
            if isinstance(item, dict):
                if item:
                    lines.append(f"{prefix}{key_text}:")
                    lines.extend(_mini_dump(item, indent + 2))
                else:
                    lines.append(f"{prefix}{key_text}: {{}}")
            elif isinstance(item, list):
                if item:
                    lines.append(f"{prefix}{key_text}:")
                    lines.extend(_mini_dump(item, indent + 2))
                else:
                    lines.append(f"{prefix}{key_text}: []")
            else:
                scalar = _scalar_dump(item)
                if scalar == "|":
                    lines.append(f"{prefix}{key_text}: |")
                    lines.extend(f"{' ' * (indent + 2)}{part}" for part in str(item).splitlines())
                else:
                    lines.append(f"{prefix}{key_text}: {scalar}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                # Inline JSON is valid YAML and keeps the fallback parser small.
                lines.append(f"{prefix}- {json.dumps(item, ensure_ascii=False)}")
            else:
                scalar = _scalar_dump(item)
                if scalar == "|":
                    lines.append(f"{prefix}- |")
                    lines.extend(f"{' ' * (indent + 2)}{part}" for part in str(item).splitlines())
                else:
                    lines.append(f"{prefix}- {scalar}")
        return lines
    return [f"{prefix}{_scalar_dump(value)}"]


def dump_data(value: Any) -> str:
    if _yaml:
        return _yaml.dump(
            value,
            Dumper=_NoAliasDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
    return "\n".join(_mini_dump(value)).rstrip() + "\n"


def _scalar_load(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "~", "None", "none"}:
        return None if value else ""
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if value.lower() in {"true", "yes"}:
        return True
    if value.lower() in {"false", "no"}:
        return False
    if value.startswith(('"', "'", "[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if value.startswith("'") and value.endswith("'"):
                return value[1:-1].replace("''", "'")
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", value):
        return float(value)
    return value


def _mini_load(text: str) -> Any:
    raw_lines = text.splitlines()
    tokens: list[tuple[int, str, int]] = []
    for number, raw in enumerate(raw_lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            raise ValueError(f"Tabs are not supported in account YAML (line {number + 1}).")
        tokens.append((indent, raw.strip(), number))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index
        is_list = tokens[index][1].startswith("-")
        container: Any = [] if is_list else {}
        while index < len(tokens):
            current_indent, content, line_no = tokens[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation on line {line_no + 1}.")
            if is_list:
                if not content.startswith("-"):
                    break
                rest = content[1:].strip()
                if rest in {"|", ">"}:
                    index += 1
                    parts: list[str] = []
                    while index < len(tokens) and tokens[index][0] > indent:
                        parts.append(tokens[index][1])
                        index += 1
                    container.append(("\n" if rest == "|" else " ").join(parts))
                    continue
                if not rest:
                    index += 1
                    child, index = parse_block(index, tokens[index][0] if index < len(tokens) else indent + 2)
                    container.append(child)
                    continue
                container.append(_scalar_load(rest))
                index += 1
                continue
            if content.startswith("-"):
                break
            if ":" not in content:
                raise ValueError(f"Expected 'key: value' on line {line_no + 1}.")
            key, rest = content.split(":", 1)
            key = key.strip().strip('"').strip("'")
            rest = rest.strip()
            if rest in {"|", ">"}:
                index += 1
                parts: list[str] = []
                while index < len(tokens) and tokens[index][0] > indent:
                    parts.append(tokens[index][1])
                    index += 1
                container[key] = ("\n" if rest == "|" else " ").join(parts)
                continue
            if rest:
                container[key] = _scalar_load(rest)
                index += 1
                continue
            index += 1
            if index < len(tokens) and tokens[index][0] > indent:
                child, index = parse_block(index, tokens[index][0])
                container[key] = child
            else:
                container[key] = {}
        return container, index

    if not tokens:
        return None
    value, index = parse_block(0, tokens[0][0])
    if index != len(tokens):
        raise ValueError(f"Could not parse account YAML near line {tokens[index][2] + 1}.")
    return value


def load_data(text: str) -> Any:
    if _yaml:
        return _yaml.safe_load(text)
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        return json.loads(text)
    return _mini_load(text)


def using_pyyaml() -> bool:
    return _yaml is not None
