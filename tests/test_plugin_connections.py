"""Tests for plugin-side connection helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONNECTION_COMMAND_PAYLOADS_PATH = REPO_ROOT / "plugin" / "commands" / "connection_command_payloads.py"
CONNECTION_EXECUTION_PATH = REPO_ROOT / "plugin" / "commands" / "connection_execution.py"


class FakeProperty:
    """Fake connection property."""

    def __init__(self, property_id: str) -> None:
        """Store a property identifier."""
        self.property_id = property_id

    def getId(self) -> str:
        """Return the property identifier."""
        return self.property_id


class FakeConnection:
    """Fake connection marker."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        return "connection"


class FakeItemNotFoundError(Exception):
    """Fake SD API ItemNotFound error."""


class FakeNode:
    """Fake connectable node."""

    def __init__(self, node_id: str, outputs: list[str], inputs: list[str], *, item_not_found: bool = False) -> None:
        """Store fake ports."""
        self.node_id = node_id
        self.outputs = outputs
        self.inputs = inputs
        self.item_not_found = item_not_found
        self.connected: tuple[str, str, str] | None = None
        self.deleted_inputs: list[str] = []

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        return self.node_id

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return fake properties for a category."""
        if category == 1:
            return [FakeProperty(port) for port in self.outputs]
        return [FakeProperty(port) for port in self.inputs]

    def newPropertyConnectionFromId(
        self, output_id: str, target_node: FakeNode, target_input_id: str
    ) -> FakeConnection:
        """Record a fake connection."""
        if self.item_not_found:
            raise FakeItemNotFoundError("SDApiError.ItemNotFound")
        self.connected = (output_id, target_node.getIdentifier(), target_input_id)
        return FakeConnection()

    def getPropertyFromId(self, property_id: str, category: int) -> FakeProperty | None:
        """Return a fake property by id."""
        properties = self.getProperties(category)
        return next((prop for prop in properties if prop.getId() == property_id), None)

    def deletePropertyConnections(self, prop: FakeProperty) -> None:
        """Record deleted input connections."""
        self.deleted_inputs.append(prop.getId())


def test_safe_connect_validates_ports_and_connects() -> None:
    """Connection helper validates visible ports before connecting."""
    module = _load_connections_module()
    source = FakeNode("source", ["out"], [])
    target = FakeNode("target", [], ["input1", "$outputsize"])

    assert module.safe_connect(source, "out", target, "input1", frozenset({"$outputsize"})) is True
    assert source.connected == ("out", "target", "input1")


def test_safe_connect_rejects_missing_output_port() -> None:
    """Connection helper rejects missing output ports."""
    module = _load_connections_module()
    source = FakeNode("source", ["out"], [])
    target = FakeNode("target", [], ["input1"])

    try:
        module.safe_connect(source, "missing", target, "input1", frozenset())
    except ValueError as exc:
        assert "Output port 'missing' not found" in str(exc)
    else:
        raise AssertionError("missing output was accepted")


def test_safe_connect_reports_parameter_properties_as_non_wire_inputs() -> None:
    """Connection helper explains ItemNotFound for visible parameter properties."""
    module = _load_connections_module()
    source = FakeNode("source", ["out"], [], item_not_found=True)
    target = FakeNode("target", [], ["opacitymult"])

    try:
        module.safe_connect(source, "out", target, "opacitymult", frozenset())
    except RuntimeError as exc:
        assert "not_a_wire_input" in str(exc)
        assert "bind_parameter_input" in str(exc)
    else:
        raise AssertionError("parameter connection failure was accepted")


def test_connection_command_payload_helpers() -> None:
    """Connection payload helpers return command-compatible results."""
    module = _load_connections_module()
    source = FakeNode("source", ["out"], [])
    target = FakeNode("target", [], ["input1"])

    connected = module.connect_nodes_payload("source", "target", source, target, "out", "input1", frozenset())
    disconnected = module.disconnect_node_input(target, "target", "input1")

    assert connected == {
        "from_node": "source",
        "from_output": "out",
        "to_node": "target",
        "to_input": "input1",
        "success": True,
    }
    assert disconnected == {"disconnected": "target:input1"}
    assert target.deleted_inputs == ["input1"]


def test_connection_payload_accepts_port_objects_and_unambiguous_defaults() -> None:
    """Connection payload accepts user-facing port objects and omitted default ports."""
    module = _load_connections_module()
    source = FakeNode("source", ["out"], [])
    target = FakeNode("target", [], ["input1"])

    object_ports = module.connect_nodes_payload(
        "source",
        "target",
        source,
        target,
        {"id": "out"},
        {"property_id": "input1"},
        frozenset(),
    )
    default_ports = module.connect_nodes_payload("source", "target", source, target, None, None, frozenset())
    disconnected = module.disconnect_node_input(target, "target", {"id": "input1"})

    assert object_ports["from_output"] == "out"
    assert object_ports["to_input"] == "input1"
    assert default_ports["from_output"] == "out"
    assert default_ports["to_input"] == "input1"
    assert disconnected == {"disconnected": "target:input1"}


def _load_connections_module() -> types.ModuleType:
    """Load concrete connection helper modules with package-relative imports enabled."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    payloads = _load_module("plugin.commands.connection_command_payloads", CONNECTION_COMMAND_PAYLOADS_PATH)
    execution = _load_module("plugin.commands.connection_execution", CONNECTION_EXECUTION_PATH)
    payloads.safe_connect = execution.safe_connect
    return payloads


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path under an explicit module name."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


def teardown_module() -> None:
    """Remove plugin modules loaded by dynamic import tests."""
    for module_name in [
        "plugin",
        "plugin.commands.connection_command_payloads",
        "plugin.commands.connection_execution",
        "plugin.commands.connection_ports",
        "plugin.commands.connection_types",
    ]:
        sys.modules.pop(module_name, None)
