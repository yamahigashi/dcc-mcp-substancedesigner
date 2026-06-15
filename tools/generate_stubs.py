#!/usr/bin/env python3
"""Generate Python type stubs from the bundled Substance Designer API HTML."""

from __future__ import annotations

import argparse
import builtins
import html
import keyword
import re
import shutil
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

KIND_CLASSES = {"class", "exception"}
KIND_CALLABLES = {"function", "method", "property"}
KIND_VALUES = {"attribute", "data"}
INHERITED_EXCEPTION_MEMBERS = {"add_note", "args", "with_traceback"}
BUILTIN_TYPES = {
    "None",
    "bool",
    "bytes",
    "float",
    "int",
    "list",
    "dict",
    "set",
    "str",
    "tuple",
}
TYPE_ALIASES = {
    "boolean": "bool",
    "callable": "Callable[..., None]",
    "integer": "int",
    "Python function": "Callable[..., None]",
    "string": "str",
    "tuple of float": "tuple[float, ...]",
    "tuple of int": "tuple[int, ...]",
}
CLASS_REGISTRY: dict[str, str] = {}
STRUCT_FIELD_ORDER = {
    "ColorRGB": ("r", "g", "b"),
    "ColorRGBA": ("r", "g", "b", "a"),
    "bool2": ("x", "y"),
    "bool3": ("x", "y", "z"),
    "bool4": ("x", "y", "z", "w"),
    "double2": ("x", "y"),
    "double3": ("x", "y", "z"),
    "double4": ("x", "y", "z", "w"),
    "float2": ("x", "y"),
    "float3": ("x", "y", "z"),
    "float4": ("x", "y", "z", "w"),
    "int2": ("x", "y"),
    "int3": ("x", "y", "z"),
    "int4": ("x", "y", "z", "w"),
}
EXTERNAL_TYPE_IMPORTS = {
    "PySide6.QtGui.QIcon": ("PySide6.QtGui", "QIcon"),
    "PySide6.QtGui.QImage": ("PySide6.QtGui", "QImage"),
    "PySide6.QtWidgets.QAction": ("PySide6.QtWidgets", "QAction"),
    "PySide6.QtWidgets.QMainWindow": ("PySide6.QtWidgets", "QMainWindow"),
    "PySide6.QtWidgets.QMenu": ("PySide6.QtWidgets", "QMenu"),
    "PySide6.QtWidgets.QToolBar": ("PySide6.QtWidgets", "QToolBar"),
    "PySide6.QtWidgets.QWidget": ("PySide6.QtWidgets", "QWidget"),
}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)

    def append(self, child: "Node | str") -> None:
        self.children.append(child)

    def text(self) -> str:
        parts: list[str] = []

        def walk(node: Node | str) -> None:
            if isinstance(node, str):
                parts.append(node)
                return
            if node.tag in {"br", "p", "div", "dd", "dt", "li"}:
                parts.append(" ")
            for child in node.children:
                walk(child)
            if node.tag in {"p", "div", "dd", "dt", "li"}:
                parts.append(" ")

        walk(self)
        return normalize("".join(parts))

    def find_all(self, tag: str | None = None, class_contains: str | None = None) -> list["Node"]:
        found: list[Node] = []

        def walk(node: Node) -> None:
            if (tag is None or node.tag == tag) and (
                class_contains is None or class_contains in node.attrs.get("class", "").split()
            ):
                found.append(node)
            for child in node.children:
                if isinstance(child, Node):
                    walk(child)

        walk(self)
        return found

    def direct_children(self, tag: str | None = None) -> list["Node"]:
        return [child for child in self.children if isinstance(child, Node) and (tag is None or child.tag == tag)]


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].append(data)


@dataclass
class Member:
    kind: str
    name: str
    params: str
    returns: str | None
    decorators: list[str] = field(default_factory=list)


@dataclass
class ClassDef:
    kind: str
    name: str
    bases: list[str] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)


@dataclass
class ModuleDef:
    name: str
    classes: list[ClassDef] = field(default_factory=list)
    functions: list[Member] = field(default_factory=list)
    values: list[Member] = field(default_factory=list)


def normalize(text: str) -> str:
    text = html.unescape(text).replace("¶", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,):\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = text.replace(" | ", " | ")
    return text.strip()


def parse_html(path: Path) -> Node:
    parser = TreeParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return parser.root


def has_py_class(node: Node, kind: str) -> bool:
    classes = node.attrs.get("class", "").split()
    return node.tag == "dl" and "py" in classes and kind in classes


def has_class(node: Node, class_name: str) -> bool:
    return class_name in node.attrs.get("class", "").split()


def first_descendant_by_class(node: Node, class_name: str) -> Node | None:
    for child in node.find_all():
        if has_class(child, class_name):
            return child
    return None


def first_direct_dt(dl: Node) -> Node | None:
    for child in dl.direct_children():
        if child.tag == "dt":
            return child
    return None


def first_direct_dd(dl: Node) -> Node | None:
    for child in dl.direct_children():
        if child.tag == "dd":
            return child
    return None


def dl_kind(dl: Node) -> str | None:
    classes = dl.attrs.get("class", "").split()
    if "py" not in classes:
        return None
    for kind in sorted(KIND_CLASSES | KIND_CALLABLES | KIND_VALUES):
        if kind in classes:
            return kind
    return None


def module_name_from_root(root: Node) -> str | None:
    for section in root.find_all("section"):
        section_id = section.attrs.get("id", "")
        if section_id.startswith("module-"):
            return section_id.removeprefix("module-")
    return None


def top_level_py_dls(root: Node) -> list[Node]:
    result: list[Node] = []
    active_class_depth = 0

    def walk(node: Node) -> None:
        nonlocal active_class_depth
        kind = dl_kind(node)
        enters_class = kind in KIND_CLASSES
        if kind and active_class_depth == 0:
            result.append(node)
        if enters_class:
            active_class_depth += 1
        for child in node.children:
            if isinstance(child, Node):
                walk(child)
        if enters_class:
            active_class_depth -= 1

    walk(root)
    return result


def signature_parts(dt: Node, dd: Node | None, full_name: str) -> tuple[str, str, str | None]:
    text = dt.text()
    text = re.sub(r"^(class|exception|static|async|abstractmethod|property)\s+", "", text)
    text = text.replace(" → ", " -> ")
    short = full_name.rsplit(".", 1)[-1]
    returns = type_from_return_node(dt)

    if returns is None and "->" in text:
        text, return_text = text.split("->", 1)
        returns = clean_type(return_text)
    if returns is None:
        returns = return_type_from_doc(dd)
    if returns is None:
        returns = infer_return_type(short)

    params = params_from_signature(dt, dd, short)
    if params is None:
        match = re.search(rf"(?:{re.escape(full_name)}|{re.escape(short)})\((.*)\)\s*$", text)
        params = clean_params(match.group(1) if match else "", dd, short)
    return short, params, returns


def params_from_signature(dt: Node, dd: Node | None, function_name: str) -> str | None:
    param_nodes = [node for node in dt.find_all() if has_class(node, "sig-param")]
    if not param_nodes:
        return None
    doc_types = param_types_from_doc(dd)
    cleaned: list[str] = []
    for index, node in enumerate(param_nodes):
        raw = normalize(node.text())
        param = clean_param(raw, index, doc_types, function_name)
        if param:
            cleaned.append(param)
    return ", ".join(cleaned)


def clean_params(params: str, dd: Node | None = None, function_name: str = "") -> str:
    params = normalize(params)
    if not params:
        return ""
    doc_types = param_types_from_doc(dd)
    parts = split_top_level(params, ",")
    cleaned: list[str] = []
    for index, part in enumerate(parts):
        param = clean_param(part, index, doc_types, function_name)
        if param:
            cleaned.append(param)
    return ", ".join(cleaned)


def clean_param(part: str, index: int, doc_types: dict[str, str], function_name: str) -> str | None:
    part = normalize(part)
    if not part:
        return None
    if part in {"*", "/"}:
        return part
    prefix = ""
    if part.startswith("**"):
        prefix = "**"
        part = part[2:]
    elif part.startswith("*"):
        prefix = "*"
        part = part[1:]

    default = None
    if "=" in part:
        part, default = part.split("=", 1)
    if ":" in part:
        name, annotation_text = part.split(":", 1)
        annotation = clean_type(annotation_text)
    else:
        name = part
        annotation = doc_types.get(normalize_name(part))
    raw_name = name.strip() or f"arg{index}"
    if annotation is None:
        annotation = infer_param_type(raw_name, default, function_name)
    name = safe_name(raw_name)
    if prefix:
        name = f"{prefix}{name}"
    suffix = " = ..." if default is not None else ""
    return f"{name}: {annotation}{suffix}" if annotation else f"{name}{suffix}"


def split_top_level(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    for index, char in enumerate(value):
        if char in "([":
            depth += 1
        elif char in ")]" and depth:
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def type_from_return_node(dt: Node) -> str | None:
    return_node = first_descendant_by_class(dt, "sig-return-typehint")
    return clean_type(return_node.text()) if return_node is not None else None


def return_type_from_doc(dd: Node | None) -> str | None:
    if dd is None:
        return None
    match = re.search(r"\bReturn type:\s*([^:]+?)(?:\s+[A-Z][A-Za-z ]+:|$)", dd.text())
    if not match:
        return None
    return clean_type(match.group(1))


def param_types_from_doc(dd: Node | None) -> dict[str, str]:
    if dd is None:
        return {}
    result: dict[str, str] = {}
    text = dd.text()
    for name, type_text in re.findall(r"\b([A-Za-z_]\w*)\s+\(([^)]+)\)\s+[–-]", text):
        annotation = clean_type(type_text)
        if annotation:
            result[normalize_name(name)] = annotation
    return result


def normalize_name(name: str) -> str:
    return safe_name(name.strip().lstrip("*"))


def clean_type(value: str) -> str | None:
    value = normalize(value)
    value = value.strip("`")
    value = value.split(" -- ", 1)[0]
    value = re.sub(r"\bclass\s+", "", value)
    value = value.replace("typing.", "")
    for src, dst in TYPE_ALIASES.items():
        if value == src:
            return dst
    value = value.replace("List[", "list[").replace("Dict[", "dict[").replace("Tuple[", "tuple[")
    value = value.replace("NoneType", "None")
    value = re.sub(r"\bOptional\[(.+)\]", r"\1 | None", value)
    value = re.sub(r"\b([a-zA-Z_]\w*)\[\]", r"list[\1]", value)
    value = re.sub(r"\s*([\[\],|])\s*", r"\1", value)
    value = value.replace("|", " | ")
    if not value:
        return None
    if value.startswith("Callable["):
        return value.replace(",", ", ")
    if "|" in value:
        parts = [clean_type(part) for part in split_top_level(value, "|")]
        return " | ".join(part for part in parts if part) or None
    if value in EXTERNAL_TYPE_IMPORTS:
        return EXTERNAL_TYPE_IMPORTS[value][1]
    if value in {"ctypes.CDLL", "logging.Filter", "logging.Formatter", "logging.Logger", "logging.LogRecord"}:
        return value
    if value == "T":
        return "_T"
    if re.fullmatch(r"[A-Za-z_]\w*(\[[^\]]+\])?", value) and base_type_name(value) in BUILTIN_TYPES:
        return value
    if "[" in value and value.endswith("]"):
        base, inner = value.split("[", 1)
        inner = inner[:-1]
        clean_base = clean_type(base)
        clean_args = [clean_type(part) for part in split_top_level(inner, ",")]
        args = [part for part in clean_args if part]
        if clean_base and args and len(args) == len(clean_args):
            return f"{clean_base}[{', '.join(args)}]"
    if re.fullmatch(r"[A-Za-z_]\w*", value) and value in CLASS_REGISTRY:
        return value
    if re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z0-9_.]+", value):
        short = value.rsplit(".", 1)[-1]
        if short in CLASS_REGISTRY:
            return short
        if value in EXTERNAL_TYPE_IMPORTS:
            return EXTERNAL_TYPE_IMPORTS[value][1]
    return infer_type_from_text(value)


def infer_type_from_text(value: str) -> str | None:
    lowered = value.lower()
    if "path" in lowered or "dir" in lowered or "file" in lowered or lowered in {"name", "identifier"}:
        return "str"
    if "count" in lowered or "index" in lowered or lowered.endswith("id"):
        return "int"
    if lowered.startswith("is") or lowered.startswith("has"):
        return "bool"
    return None


def infer_return_type(name: str) -> str | None:
    exact = {
        "acquire": "None",
        "addFilter": "None",
        "alignSDNodes": "None",
        "close": "None",
        "createLock": "None",
        "emit": "None",
        "exportSDGraphOutputs": "None",
        "filter": "bool",
        "flush": "None",
        "format": "str",
        "getCAPI": "CAPI",
        "getCTypesBinary": "ctypes.CDLL",
        "getCTypesFct": "Callable[..., int]",
        "getCurrentGraphSelection": "SDArray[SDGraphObject] | None",
        "getCurrentGraphSelectionFromGraphViewID": "SDArray[SDGraphObject] | None",
        "getFunction": "Callable[..., int]",
        "getLogger": "logging.Logger",
        "get_name": "str",
        "getOSBackend": "OSBackend",
        "getQtForPythonUIMgr": "QtForPythonUIMgrWrapper",
        "getSDAppInfo": "SDAppInfo",
        "handle": "bool",
        "handleError": "None",
        "loadCTypesBinary": "ctypes.CDLL",
        "main": "None",
        "moveStackedNodes": "None",
        "name": "str",
        "removeFilter": "None",
        "snapSDNodes": "None",
        "stackNodesHorizontal": "dict[int, list[GraphNode]]",
        "UndoGroup": "None",
        "updateGeometryPositions": "None",
    }
    if name in exact:
        return exact[name]
    if name.startswith(("set", "delete", "release", "registerPaths", "register")):
        return "None"
    if name.startswith(("is", "has")):
        return "bool"
    if name.startswith("get") and any(
        token in name for token in ("Path", "Dir", "File", "Url", "Version", "Identifier", "Name")
    ):
        return "str"
    if name.startswith(("count", "index", "getSize")):
        return "int"
    return None


def infer_param_type(name: str, default: str | None, function_name: str) -> str | None:
    clean = normalize_name(name)
    exact = {
        "aAlignDirection": "AlignmentDirection",
        "aBinaryFile": "str",
        "aFctName": "str",
        "aFileExt": "str",
        "aFunctionName": "str",
        "aOutputDir": "str",
        "aPyFile": "str | None",
        "aReferenceFile": "str",
        "aSDContext": "Context",
        "aSDGraph": "SDGraph",
        "aSDNodeSpace": "float",
        "aSnapSize": "float",
        "aSubDirName": "str",
        "action": "QAction",
        "callable": "Callable[..., None]",
        "callable_": "Callable[..., None]",
        "callbackID": "int",
        "channelName": "str | None",
        "filter": "logging.Filter",
        "filter_": "logging.Filter",
        "fmt": "logging.Formatter",
        "kwargs": "int | str",
        "level": "int | str",
        "name": "str",
        "record": "logging.LogRecord",
        "sortedGraphNodes": "list[list[GraphNode]]",
        "start": "int",
        "stop": "int",
        "stream": "TextIO",
        "toolbar": "QToolBar",
        "value": "_T",
    }
    if clean in exact:
        return exact[clean]
    if default is not None:
        stripped = default.strip()
        if stripped in {"''", '""', "None"}:
            return "str | None" if stripped == "None" else "str"
        if re.fullmatch(r"\d+", stripped):
            return "int"
        if re.fullmatch(r"\d+\.\d+", stripped):
            return "float"
    if clean.lower().endswith(("name", "title", "path", "dir", "file", "ext")):
        return "str"
    if clean.lower().endswith("id"):
        return "int"
    if function_name in {"count", "index"} and clean == "value":
        return "_T"
    return None


def base_type_name(value: str) -> str:
    return value.split("[", 1)[0]


def safe_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\W+", "_", name)
    if not name:
        return "arg"
    if name[0].isdigit():
        name = f"arg_{name}"
    if name in dir(builtins):
        name += "_"
    if keyword.iskeyword(name):
        name += "_"
    return name


def extract_bases(dd: Node | None) -> list[str]:
    if dd is None:
        return []
    for child in dd.direct_children("p"):
        text = child.text()
        if text.startswith("Bases:"):
            bases = [clean_type(item) for item in split_top_level(text.removeprefix("Bases:"), ",")]
            return [base for base in bases if base]
    return []


def parse_member(dl: Node, module_name: str, class_name: str | None = None) -> Member | None:
    kind = dl_kind(dl)
    dt = first_direct_dt(dl)
    if not kind or dt is None:
        return None
    full_id = dt.attrs.get("id", "")
    if not full_id:
        return None
    dd = first_direct_dd(dl)
    name, params, returns = signature_parts(dt, dd, full_id)
    decorators: list[str] = []
    text = dt.text()
    if "static " in text:
        decorators.append("staticmethod")
    if kind == "property":
        decorators.append("property")
    if kind in KIND_VALUES:
        params = ""
    return Member(kind=kind, name=name, params=params, returns=returns, decorators=decorators)


def parse_class(dl: Node, module_name: str) -> ClassDef | None:
    kind = dl_kind(dl)
    dt = first_direct_dt(dl)
    if kind not in KIND_CLASSES or dt is None:
        return None
    full_id = dt.attrs.get("id", "")
    if not full_id:
        return None
    dd = first_direct_dd(dl)
    name, _, _ = signature_parts(dt, dd, full_id)
    class_def = ClassDef(kind=kind, name=name, bases=extract_bases(dd))
    if kind == "exception" and not class_def.bases:
        class_def.bases = ["Exception"]
    if dd is None:
        return class_def
    for child in dd.direct_children("dl"):
        member = parse_member(child, module_name, class_def.name)
        if kind == "exception" and member is not None and member.name in INHERITED_EXCEPTION_MEMBERS:
            continue
        if member is not None:
            class_def.members.append(member)
    return class_def


def parse_module(path: Path) -> ModuleDef | None:
    root = parse_html(path)
    module_name = module_name_from_root(root)
    if not module_name:
        return None
    module = ModuleDef(module_name)
    for dl in top_level_py_dls(root):
        kind = dl_kind(dl)
        if kind in KIND_CLASSES:
            class_def = parse_class(dl, module_name)
            if class_def is not None:
                module.classes.append(class_def)
        elif kind in KIND_CALLABLES:
            member = parse_member(dl, module_name)
            if member is not None:
                module.functions.append(member)
        elif kind in KIND_VALUES:
            member = parse_member(dl, module_name)
            if member is not None:
                module.values.append(member)
    return module


def render_module(module: ModuleDef) -> str:
    lines = [
        "# Generated from Adobe Substance 3D Designer Python API HTML.",
        "from __future__ import annotations",
        "",
        "from collections.abc import Iterable, Iterator",
        "from typing import Callable, ClassVar, Generic, TextIO, TypeVar",
    ]
    imports = referenced_imports(module)
    module_imports = referenced_module_imports(module)
    if imports:
        lines.append("")
        for imported_module, names in imports:
            lines.append(f"from {imported_module} import {', '.join(names)}")
    if module_imports:
        lines.append("")
        for imported_module in module_imports:
            lines.append(f"import {imported_module}")
    lines.append("")
    if module_needs_typevar(module):
        lines.append('_T = TypeVar("_T")')
        lines.append("")
    for value in unique_members(module.values):
        annotation = infer_value_type(value.name)
        lines.append(f"{value.name}: {annotation}" if annotation else value.name)
    if module.values:
        lines.append("")
    for func in unique_members(module.functions):
        lines.extend(render_callable(func, indent=""))
        lines.append("")
    for cls in module.classes:
        lines.extend(render_class(cls))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def module_needs_typevar(module: ModuleDef) -> bool:
    return "_T" in module_annotation_text(module)


def module_annotation_text(module: ModuleDef) -> str:
    return " ".join(
        [
            *(value.returns or "" for value in module.values),
            *(func.params + " " + (func.returns or "") for func in module.functions),
            *(
                " ".join(
                    [
                        *cls.bases,
                        *(member.params + " " + (member.returns or "") for member in cls.members),
                    ]
                )
                for cls in module.classes
            ),
        ]
    )


def referenced_imports(module: ModuleDef) -> list[tuple[str, list[str]]]:
    local_names = {cls.name for cls in module.classes}
    referenced: set[str] = set()

    def collect(annotation: str) -> None:
        for token in re.findall(r"\b[A-Za-z_]\w*\b", annotation):
            if token in CLASS_REGISTRY and token not in local_names:
                referenced.add(token)

    for value in module.values:
        if value.returns:
            collect(value.returns)
    for func in module.functions:
        if func.returns:
            collect(func.returns)
        for param in split_top_level(func.params, ","):
            if ":" in param:
                collect(param.split(":", 1)[1])
    for cls in module.classes:
        for base in cls.bases:
            collect(base)
        for member in cls.members:
            if member.returns:
                collect(member.returns)
            for param in split_top_level(member.params, ","):
                if ":" in param:
                    collect(param.split(":", 1)[1])

    by_module: dict[str, list[str]] = {}
    for name in sorted(referenced):
        by_module.setdefault(CLASS_REGISTRY[name], []).append(name)
    for imported_module, imported_name in referenced_external_imports(module):
        by_module.setdefault(imported_module, []).append(imported_name)
    return sorted(by_module.items())


def referenced_external_imports(module: ModuleDef) -> list[tuple[str, str]]:
    text = module_annotation_text(module)
    result: set[tuple[str, str]] = set()
    for full_name, import_info in EXTERNAL_TYPE_IMPORTS.items():
        if full_name in text or import_info[1] in text:
            result.add(import_info)
    return sorted(result)


def referenced_module_imports(module: ModuleDef) -> list[str]:
    text = module_annotation_text(module)
    return [imported_module for imported_module in ("ctypes", "logging") if f"{imported_module}." in text]


def unique_members(members: Iterable[Member]) -> list[Member]:
    seen: set[tuple[str, str]] = set()
    result: list[Member] = []
    for member in members:
        key = (member.kind, member.name)
        if key in seen:
            continue
        seen.add(key)
        result.append(member)
    return result


def render_class(cls: ClassDef) -> list[str]:
    base_list = [*cls.bases]
    if cls.name == "SDArray":
        base_list.append("Iterable[_T]")
    bases = f"({', '.join(base_list)})" if base_list else ""
    lines = [f"class {cls.name}{bases}:"]
    if cls.name in STRUCT_FIELD_ORDER:
        lines.extend(render_struct_members(cls))
        return lines
    if cls.name == "SDArray":
        lines.extend(
            [
                "    def __iter__(self) -> Iterator[_T]: ...",
                "    def __len__(self) -> int: ...",
                "    def __getitem__(self, index: int) -> _T: ...",
            ]
        )
    rendered_members: list[str] = []
    for member in unique_members(cls.members):
        rendered_members.extend(render_member(member))
    if not rendered_members:
        lines.append("    ...")
    else:
        lines.extend(rendered_members)
    return lines


def render_struct_members(cls: ClassDef) -> list[str]:
    field_type = struct_field_type(cls.name)
    ordered_fields = STRUCT_FIELD_ORDER[cls.name]
    params = ", ".join(f"{name}: {field_type} = ..." for name in ordered_fields)
    lines = [f"    def __init__(self, {params}) -> None: ..."]
    for field_name in ordered_fields:
        lines.append(f"    {field_name}: {field_type}")
    return lines


def struct_field_type(class_name: str) -> str:
    if class_name.startswith("bool"):
        return "bool"
    if class_name.startswith("int"):
        return "int"
    return "float"


def render_member(member: Member) -> list[str]:
    if member.kind in KIND_VALUES:
        annotation = infer_value_type(member.name)
        return [f"    {member.name}: ClassVar[{annotation}]" if annotation else f"    {member.name}: ClassVar"]
    return render_callable(member, indent="    ")


def infer_value_type(name: str) -> str | None:
    lowered = name.lower()
    if lowered in {"terminator", "name"} or lowered.endswith("dir") or lowered.endswith("path"):
        return "str"
    if lowered in {"true", "false"}:
        return "bool"
    return "int"


def render_callable(member: Member, indent: str) -> list[str]:
    lines: list[str] = []
    for decorator in member.decorators:
        lines.append(f"{indent}@{decorator}")
    params = member.params
    if indent and "staticmethod" not in member.decorators and "property" not in member.decorators:
        params = f"self{', ' if params else ''}{params}"
    if "property" in member.decorators:
        params = "self"
    return_annotation = f" -> {member.returns}" if member.returns else ""
    lines.append(f"{indent}def {member.name}({params}){return_annotation}: ...")
    return lines


def module_to_path(module_name: str, out_dir: Path) -> Path:
    parts = module_name.split(".")
    return out_dir.joinpath(*parts).with_suffix(".pyi")


def write_package_inits(paths: Iterable[Path], out_dir: Path) -> None:
    dirs = {path.parent for path in paths}
    for path in list(dirs):
        current = path
        while current != out_dir.parent and out_dir in (current, *current.parents):
            dirs.add(current)
            if current == out_dir:
                break
            current = current.parent
    for directory in dirs:
        init_path = directory / "__init__.pyi"
        if directory == out_dir / "sd":
            init_path.write_text(
                "# Generated package marker.\n"
                "from __future__ import annotations\n"
                "\n"
                "from sd.context import Context\n"
                "\n"
                "def getContext() -> Context: ...\n",
                encoding="utf-8",
            )
        elif not init_path.exists():
            init_path.write_text("# Generated package marker.\n", encoding="utf-8")


def collect_class_registry(html_root: Path) -> dict[str, str]:
    registry: dict[str, str] = {}
    for path in sorted((html_root / "pythonapi" / "api").rglob("*.html")):
        root = parse_html(path)
        module_name = module_name_from_root(root)
        if not module_name:
            continue
        for dl in top_level_py_dls(root):
            kind = dl_kind(dl)
            if kind not in KIND_CLASSES:
                continue
            dt = first_direct_dt(dl)
            if dt is None:
                continue
            full_id = dt.attrs.get("id", "")
            if full_id:
                registry.setdefault(full_id.rsplit(".", 1)[-1], module_name)
    return registry


def generate(html_root: Path, out_dir: Path, clean: bool) -> list[Path]:
    global CLASS_REGISTRY
    CLASS_REGISTRY = collect_class_registry(html_root)
    if clean and out_dir.exists():
        clear_output_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    helper_path = out_dir / "_substance_stub_types.pyi"
    if helper_path.exists():
        helper_path.unlink()
    write_external_stubs(out_dir)
    written: list[Path] = []
    for path in sorted((html_root / "pythonapi" / "api").rglob("*.html")):
        module = parse_module(path)
        if module is None:
            continue
        out_path = module_to_path(module.name, out_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_module(module), encoding="utf-8")
        written.append(out_path)
    write_package_inits(written, out_dir)
    return written


def clear_output_dir(out_dir: Path) -> None:
    try:
        shutil.rmtree(out_dir)
        return
    except PermissionError:
        pass
    for path in sorted(out_dir.rglob("*.pyi"), reverse=True):
        path.unlink()


def write_external_stubs(out_dir: Path) -> None:
    qt_gui = out_dir / "PySide6" / "QtGui.pyi"
    qt_widgets = out_dir / "PySide6" / "QtWidgets.pyi"
    qt_gui.parent.mkdir(parents=True, exist_ok=True)
    qt_gui.write_text("class QIcon:\n    ...\n\nclass QImage:\n    ...\n", encoding="utf-8")
    qt_widgets.write_text(
        "class QAction:\n"
        "    ...\n"
        "\n"
        "class QMainWindow:\n"
        "    ...\n"
        "\n"
        "class QMenu:\n"
        "    ...\n"
        "\n"
        "class QToolBar:\n"
        "    ...\n"
        "\n"
        "class QWidget:\n"
        "    ...\n",
        encoding="utf-8",
    )
    (out_dir / "PySide6" / "__init__.pyi").write_text("# Generated package marker.\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-root", type=Path, default=Path("html"))
    parser.add_argument("--out-dir", type=Path, default=Path("stubs"))
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()
    written = generate(args.html_root, args.out_dir, clean=not args.no_clean)
    print(f"generated {len(written)} stub modules under {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
