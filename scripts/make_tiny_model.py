#!/usr/bin/env python3
"""Generates a tiny synthetic ONNX "segmentation" model fixture for tests.

The model is intentionally trivial (a threshold turned into a mask via a
single Greater + Cast node graph) rather than a trained network: the test
suite exercises the inference *pipeline* (spec validation, digest checking,
provenance, determinism), not model accuracy.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import onnx
from onnx import TensorProto, helper


def build_model() -> onnx.ModelProto:
    dims = [1, 1, 128, 128, 128]

    input_tensor = helper.make_tensor_value_info("input", TensorProto.FLOAT, dims)
    output_tensor = helper.make_tensor_value_info("output", TensorProto.FLOAT, dims)

    threshold = helper.make_tensor("threshold", TensorProto.FLOAT, [], [0.0])

    greater_node = helper.make_node("Greater", ["input", "threshold"], ["mask_bool"])
    cast_node = helper.make_node(
        "Cast", ["mask_bool"], ["output"], to=TensorProto.FLOAT
    )

    graph = helper.make_graph(
        [greater_node, cast_node],
        "tiny_seg",
        [input_tensor],
        [output_tensor],
        initializer=[threshold],
    )

    model = helper.make_model(
        graph,
        producer_name="mivw-fixture-generator",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(build_model(), args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
