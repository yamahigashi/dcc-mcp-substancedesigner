"""Static node and parameter catalogs used by the host plugin."""

from __future__ import annotations

from typing import TypeAlias

PortList: TypeAlias = list[str]
AtomicPortSpec: TypeAlias = dict[str, PortList]

SYSTEM_PARAMS: frozenset[str] = frozenset(
    {"$outputsize", "$format", "$pixelsize", "$pixelratio", "$tiling", "$randomseed", "$time"}
)

ATOMIC_PORTS: dict[str, AtomicPortSpec] = {
    "sbs::compositing::blend": {
        "inputs": ["source", "destination", "opacity"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::levels": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::curve": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::hsl": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::blur": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::sharpen": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::warp": {
        "inputs": ["input1", "inputgradient"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::directionalwarp": {
        "inputs": ["input1", "inputintensity"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::normal": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::transformation": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::distance": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::grayscaleconversion": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::shuffle": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::emboss": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::passthrough": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::uniform": {
        "inputs": [],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::output": {
        "inputs": ["inputNodeOutput"],
        "outputs": [],
    },
    "sbs::compositing::input_color": {
        "inputs": [],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::input_grayscale": {
        "inputs": [],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::gradient": {
        "inputs": ["input1", "gradient"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::pixelprocessor": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
    "sbs::compositing::fxmaps": {
        "inputs": ["input1"],
        "outputs": ["unique_filter_output"],
    },
}

BLEND_MODES: dict[str, int] = {
    "copy": 0,
    "normal": 0,
    "add": 1,
    "linear_dodge": 1,
    "subtract": 2,
    "multiply": 3,
    "max": 4,
    "lighten": 4,
    "min": 5,
    "darken": 5,
    "overlay": 9,
    "screen": 10,
    "soft_light": 11,
    "hard_light": 12,
    "divide": 13,
    "difference": 14,
}
