"""Preview output selection, texture saving, temporary output, and image resizing helpers."""

from __future__ import annotations

import importlib
import os
from typing import cast

from sd.api.sdbasetypes import float2
from sd.api.sdproperty import SDPropertyCategory
from sd.api.sdvaluestring import SDValueString

from ..parameters.parameter_types import SettableSDValue
from ..parameters.sd_values import make_sd_value_usage_array
from .preview_types import (
    ClassNamed,
    OutputProperty,
    PositionValue,
    PreviewNode,
    QtCoreImageModule,
    QtGuiImageModule,
    QtImageModules,
    ReprFallback,
    SaveMethod,
    SourcePreviewNode,
    TemporaryOutputGraph,
    TemporaryOutputNode,
    TextureConvertible,
    ValueContainer,
)


def output_properties(node: PreviewNode) -> list[OutputProperty]:
    """Return output properties for a preview node."""
    try:
        return list(node.getProperties(SDPropertyCategory.Output))
    except Exception:
        return []


def find_node_output_property(node: PreviewNode, property_id: str | None = None) -> OutputProperty:
    """Return the requested output property or the first texture-like output."""
    outputs = output_properties(node)
    if not outputs:
        raise ValueError("Node '{}' has no output properties.".format(node.getIdentifier()))
    if property_id:
        for prop in outputs:
            try:
                if prop.getId() == property_id:
                    return prop
            except Exception:
                pass
        raise ValueError(
            "Output '{}' not found on node '{}'. Available: {}".format(
                property_id,
                node.getIdentifier(),
                sorted([prop.getId() for prop in outputs]),
            )
        )
    texture_outputs = [prop for prop in outputs if is_texture_output_property(prop)]
    if texture_outputs:
        return texture_outputs[0]
    return outputs[0]


def require_texture_output_property(node: PreviewNode, prop: OutputProperty) -> None:
    """Raise when a property has a known non-texture output type."""
    if is_texture_output_property(prop):
        return
    prop_type = get_property_type_id(prop)
    if prop_type:
        raise ValueError(
            "Node output '{}.{}' is not a texture output (type: {}).".format(
                node.getIdentifier(),
                prop.getId(),
                prop_type,
            )
        )


def is_texture_output_property(prop: OutputProperty) -> bool:
    """Return whether an output property appears to contain texture data."""
    prop_type = get_property_type_id(prop)
    if not prop_type:
        return False
    lowered = prop_type.lower()
    return "texture" in lowered or "bitmap" in lowered or "image" in lowered


def get_property_type_id(prop: OutputProperty) -> str:
    """Return a best-effort SD type identifier for a property."""
    try:
        prop_type = prop.getType()
        if prop_type is None:
            return ""
        try:
            return prop_type.getId()
        except Exception:
            return str(prop_type)
    except Exception:
        return ""


def save_node_preview_texture(value: ReprFallback, image_path: str, node_id: str, output_id: str) -> None:
    """Save an SD texture-like preview value to a PNG path."""
    texture_candidates: list[ReprFallback] = []
    if hasattr(value, "toSDTexture"):
        try:
            texture_candidates.append(cast(TextureConvertible, value).toSDTexture())
        except BaseException:
            pass
    if hasattr(value, "get"):
        try:
            raw = cast(ValueContainer, value).get()
            texture_candidates.append(raw)
            if hasattr(raw, "toSDTexture"):
                try:
                    texture_candidates.append(cast(TextureConvertible, raw).toSDTexture())
                except BaseException:
                    pass
        except BaseException:
            pass

    for texture in texture_candidates:
        for method_name in ("save", "saveAs"):
            save_method = getattr(texture, method_name, None)
            if save_method is None:
                continue
            try:
                cast(SaveMethod, save_method)(image_path)
                return
            except BaseException:
                pass

    value_class = safe_class_name(value)
    candidate_classes = [safe_class_name(candidate) for candidate in texture_candidates]
    raise RuntimeError(
        "Node output '{}.{}' did not expose a saveable texture (value class: {}, candidates: {}).".format(
            node_id,
            output_id,
            value_class,
            candidate_classes or "none",
        )
    )


def export_node_output_texture(
    graph: TemporaryOutputGraph,
    node: PreviewNode,
    output_prop: OutputProperty,
    file_path: str,
) -> dict[str, str]:
    """Compute and save a texture-like node output to a caller-provided path."""
    require_texture_output_property(node, output_prop)
    node_id = node.getIdentifier()
    output_id = output_prop.getId()
    normalized_path = os.path.abspath(str(file_path))
    directory = os.path.dirname(normalized_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    graph.compute()
    value = cast(TemporaryOutputNode, node).getPropertyValue(output_prop)
    save_node_preview_texture(value, normalized_path, node_id, output_id)
    if not os.path.exists(normalized_path):
        raise RuntimeError("Node output export was not created: {}".format(normalized_path))
    return {
        "node_id": node_id,
        "node_output_id": output_id,
        "file_path": normalized_path,
        "format": os.path.splitext(normalized_path)[1].lstrip(".").lower() or "unknown",
    }


def safe_class_name(value: ReprFallback | None) -> str:
    """Return a best-effort class name for diagnostic messages."""
    if value is None:
        return "None"
    try:
        return cast(ClassNamed, value).getClassName()
    except BaseException:
        return type(value).__name__


def save_node_preview_via_temporary_output(
    graph: TemporaryOutputGraph,
    node: SourcePreviewNode,
    output_id: str,
    image_path: str,
) -> None:
    """Save a node preview by wiring a temporary output node."""
    temp_node: TemporaryOutputNode | None = None
    try:
        temp_node = create_temporary_output_node(graph, node, output_id)
        connect_temporary_output_node(node, output_id, temp_node)
        graph.compute()
        save_temporary_output_texture(node, output_id, temp_node, image_path)
    finally:
        if temp_node is not None:
            try:
                graph.deleteNode(temp_node)
            except BaseException:
                pass


def create_temporary_output_node(
    graph: TemporaryOutputGraph,
    node: SourcePreviewNode,
    output_id: str,
) -> TemporaryOutputNode:
    """Create and configure a temporary graph output node for preview rendering."""
    temp_node = graph.newNode("sbs::compositing::output")
    if temp_node is None:
        raise RuntimeError("Failed to create temporary output node for preview.")

    try:
        temp_node.setPosition(cast(PositionValue, float2(-10000.0, -10000.0)))
    except BaseException:
        pass

    temp_identifier = "mcp_preview_{}_{}".format(node.getIdentifier(), output_id)
    for annotation_id, annotation_value in (
        ("label", temp_identifier),
        ("identifier", temp_identifier),
        ("usages", temp_identifier),
    ):
        try:
            annotation = (
                make_sd_value_usage_array(annotation_value)
                if annotation_id == "usages"
                else cast(SettableSDValue, SDValueString.sNew(annotation_value))
            )
            temp_node.setAnnotationPropertyValueFromId(
                annotation_id,
                annotation,
            )
        except BaseException:
            pass

    return temp_node


def connect_temporary_output_node(
    node: SourcePreviewNode,
    output_id: str,
    temp_node: TemporaryOutputNode,
) -> None:
    """Connect a source node output to the temporary graph output node."""
    conn = node.newPropertyConnectionFromId(output_id, temp_node, "inputNodeOutput")
    if conn is None:
        raise RuntimeError(
            "Failed to connect temporary preview output: {}.{} -> {}.inputNodeOutput".format(
                node.getIdentifier(),
                output_id,
                temp_node.getIdentifier(),
            )
        )


def save_temporary_output_texture(
    node: SourcePreviewNode,
    output_id: str,
    temp_node: TemporaryOutputNode,
    image_path: str,
) -> None:
    """Save the first texture value exposed by a temporary output node."""
    output_props = temporary_output_properties(temp_node)
    if not output_props:
        raise RuntimeError("Temporary preview output node did not expose output properties.")

    last_error: BaseException | None = None
    for prop in output_props:
        try:
            value = temp_node.getPropertyValue(prop)
            if value is None:
                continue
            save_node_preview_texture(value, image_path, temp_node.getIdentifier(), prop.getId())
            return
        except BaseException as exc:
            last_error = exc
    if last_error is not None:
        raise RuntimeError(
            "Temporary preview output failed for '{}.{}': {}".format(
                node.getIdentifier(),
                output_id,
                last_error,
            )
        )
    raise RuntimeError(
        "Temporary preview output for '{}.{}' did not produce a value.".format(
            node.getIdentifier(),
            output_id,
        )
    )


def temporary_output_properties(node: TemporaryOutputNode) -> list[OutputProperty]:
    """Return temporary output node properties, tolerating host API failures."""
    try:
        return list(node.getProperties(SDPropertyCategory.Output))
    except BaseException:
        return []


def normalize_preview_image_size(image_path: str, width: int, height: int, qt_binding: str | None) -> None:
    """Resize a saved preview PNG to the requested dimensions when Qt is available."""
    modules = import_image_modules(qt_binding)
    if modules is None:
        return
    qtgui, qtcore = modules
    image = qtgui.QImage(image_path)
    if image.isNull():
        raise RuntimeError("Node preview PNG could not be read after save: {}".format(image_path))
    if image.width() == int(width) and image.height() == int(height):
        return
    scaled = image.scaled(
        int(width),
        int(height),
        qtcore.Qt.IgnoreAspectRatio,
        qtcore.Qt.SmoothTransformation,
    )
    if scaled.isNull() or not scaled.save(image_path, "PNG"):
        raise RuntimeError(
            "Node preview PNG could not be resized to {}x{}: {}".format(
                int(width),
                int(height),
                image_path,
            )
        )


def import_image_modules(qt_binding: str | None) -> QtImageModules | None:
    """Import matching QtGui and QtCore modules for preview image operations."""
    core_binding = qt_binding or "PySide6.QtCore"
    gui_binding = core_binding.replace(".QtCore", ".QtGui")
    try:
        qtgui = cast(QtGuiImageModule, importlib.import_module(gui_binding))
        qtcore = cast(QtCoreImageModule, importlib.import_module(core_binding))
        return qtgui, qtcore
    except BaseException:
        return None
