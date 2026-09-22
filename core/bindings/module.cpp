#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include "mivw/dicom/deidentifier.hpp"
#include "mivw/infer/runtime.hpp"
#include "mivw/render/renderer.hpp"
#include "mivw/volume/volume.hpp"

namespace py = pybind11;
using namespace mivw;

namespace {

/// Typed exceptions so the API layer can map failures to problem details
/// instead of surfacing a bare RuntimeError.
void registerExceptions(py::module_ &m) {
  static py::exception<std::exception> base(m, "MivwError");
  py::register_exception<dicom::DeIdentificationError>(
      m, "DeIdentificationError", base);
  py::register_exception<render::DeviceLostError>(m, "DeviceLostError", base);
  py::register_exception<infer::SpecMismatchError>(m, "SpecMismatchError",
                                                   base);
  py::register_exception<infer::DigestMismatchError>(m, "DigestMismatchError",
                                                     base);
}

/// A raw 32-byte SHA-256 digest, not a hex string: callers already carry the
/// digest as bytes (from the model registry / storage layer), and re-parsing
/// hex here would just be one more place for an off-by-one to hide.
std::array<std::uint8_t, 32> sha256ArrayFromBytes(const py::bytes &raw) {
  const std::string data = raw;
  if (data.size() != 32) {
    throw std::invalid_argument("sha256 digest must be exactly 32 bytes");
  }
  std::array<std::uint8_t, 32> out{};
  std::copy(data.begin(), data.end(), reinterpret_cast<char *>(out.data()));
  return out;
}

/// Mirrors `InputSpec.model_dump(by_alias=True)` on the Python side
/// (mivw_api.schemas.model.InputSpec): shape, spacingMm, orientation,
/// spacingToleranceMm and an optional normalisation block.
infer::InputSpec inputSpecFromDict(const py::dict &spec) {
  infer::InputSpec out;

  out.shape = spec["shape"].cast<std::vector<std::int64_t>>();

  const auto spacing = spec["spacingMm"].cast<std::vector<double>>();
  if (spacing.size() != 3) {
    throw std::invalid_argument("spacingMm must have exactly 3 elements");
  }
  std::copy(spacing.begin(), spacing.end(), out.spacingMm.begin());

  if (spec.contains("orientation")) {
    out.orientation = spec["orientation"].cast<std::string>();
  }
  if (spec.contains("spacingToleranceMm")) {
    out.spacingToleranceMm = spec["spacingToleranceMm"].cast<double>();
  }

  if (spec.contains("normalisation") && !spec["normalisation"].is_none()) {
    const auto norm = spec["normalisation"].cast<py::dict>();
    const std::string kind =
        norm.contains("kind") ? norm["kind"].cast<std::string>() : "zscore";
    out.normalisation = kind == "none"     ? infer::Normalisation::None
                        : kind == "minmax" ? infer::Normalisation::MinMax
                                           : infer::Normalisation::ZScore;
    if (norm.contains("clipHu") && !norm["clipHu"].is_none()) {
      const auto clip = norm["clipHu"].cast<std::vector<double>>();
      if (clip.size() == 2) {
        out.clipHu = {static_cast<float>(clip[0]), static_cast<float>(clip[1])};
      }
    }
  }

  return out;
}

} // namespace

PYBIND11_MODULE(mivw_core, m) {
  m.doc() = "MIVW compute core: DICOM, volume processing, inference and Vulkan "
            "rendering";
  m.attr("__version__") = "0.1.0";

  registerExceptions(m);

  py::enum_<volume::DType>(m, "DType")
      .value("Int16", volume::DType::Int16)
      .value("UInt16", volume::DType::UInt16)
      .value("Float32", volume::DType::Float32);

  py::class_<volume::Volume>(m, "Volume")
      .def(py::init<volume::Dims3, volume::Vec3, volume::DType>())
      .def_property_readonly("dims", &volume::Volume::dims)
      .def_property_readonly("spacing", &volume::Volume::spacing)
      .def_property_readonly("origin", &volume::Volume::origin)
      .def_property_readonly("size_bytes", &volume::Volume::sizeBytes)
      // Zero-copy numpy view. The buffer stays owned by C++; the keep_alive
      // policy prevents the volume outliving the array. Dtype must be
      // dispatched at runtime: inference output volumes are Float32, not
      // the Int16 every render-path volume happens to be.
      .def(
          "as_array",
          [](volume::Volume &self) -> py::object {
            const auto &d = self.dims();
            const std::array<py::ssize_t, 3> shape{d[2], d[1], d[0]};
            switch (self.dtype()) {
            case volume::DType::Int16:
              return py::array_t<std::int16_t>(
                  shape, reinterpret_cast<std::int16_t *>(self.bytes().data()),
                  py::cast(self));
            case volume::DType::UInt16:
              return py::array_t<std::uint16_t>(
                  shape, reinterpret_cast<std::uint16_t *>(self.bytes().data()),
                  py::cast(self));
            case volume::DType::Float32:
              return py::array_t<float>(
                  shape, reinterpret_cast<float *>(self.bytes().data()),
                  py::cast(self));
            }
            throw std::logic_error("unhandled Volume dtype");
          },
          py::keep_alive<0, 1>());

  m.def("resample_isotropic", &volume::resampleIsotropic, py::arg("volume"),
        py::arg("target_spacing_mm"),
        // Resampling a large volume takes far longer than the ~100us GIL
        // release threshold, so hold no lock while it runs.
        py::call_guard<py::gil_scoped_release>());

  py::class_<render::Camera>(m, "Camera")
      .def(py::init<>())
      .def_readwrite("eye", &render::Camera::eye)
      .def_readwrite("target", &render::Camera::target)
      .def_readwrite("up", &render::Camera::up)
      .def_readwrite("fov_degrees", &render::Camera::fovDegrees);

  py::enum_<render::Quality>(m, "Quality")
      .value("Interactive", render::Quality::Interactive)
      .value("Still", render::Quality::Still);

  py::class_<render::RenderParams>(m, "RenderParams")
      .def(py::init<>())
      .def_readwrite("camera", &render::RenderParams::camera)
      .def_readwrite("quality", &render::RenderParams::quality)
      .def_readwrite("width", &render::RenderParams::width)
      .def_readwrite("height", &render::RenderParams::height)
      .def_readwrite("transfer_function_preset",
                     &render::RenderParams::transferFunctionPreset)
      .def_readwrite("segmentation_visible",
                     &render::RenderParams::segmentationVisible)
      .def_readwrite("segmentation_opacity",
                     &render::RenderParams::segmentationOpacity);

  py::class_<render::Renderer>(m, "Renderer")
      .def(py::init<>())
      .def("set_volume", &render::Renderer::setVolume, py::arg("volume"),
           py::call_guard<py::gil_scoped_release>())
      .def(
          "set_segmentation",
          [](render::Renderer &self, const volume::Volume &mask,
             const py::sequence &labelColours) {
            std::vector<std::array<float, 4>> colours;
            colours.reserve(static_cast<std::size_t>(py::len(labelColours)));
            for (const auto &item : labelColours) {
              const auto rgba = item.cast<std::vector<float>>();
              if (rgba.size() != 4) {
                throw std::invalid_argument(
                    "each label colour must have 4 components (r, g, b, a)");
              }
              colours.push_back({rgba[0], rgba[1], rgba[2], rgba[3]});
            }
            py::gil_scoped_release release;
            self.setSegmentation(mask, colours);
          },
          py::arg("mask"), py::arg("label_colours"))
      .def(
          "render",
          [](render::Renderer &self, const render::RenderParams &params,
             std::uint32_t sequence) {
            render::Frame frame;
            {
              py::gil_scoped_release release;
              frame = self.render(params, sequence);
            }
            return py::make_tuple(
                py::bytes(reinterpret_cast<const char *>(frame.payload.data()),
                          frame.payload.size()),
                frame.sequence, frame.width, frame.height, frame.renderTimeUs,
                frame.codec);
          },
          py::arg("params"), py::arg("sequence"))
      .def("recover_from_device_lost", &render::Renderer::recoverFromDeviceLost)
      .def_property_readonly("gpu_memory_bytes",
                             &render::Renderer::gpuMemoryBytes);

  py::class_<infer::InferenceRuntime>(m, "InferenceRuntime")
      .def(py::init<>())
      .def_static("is_device_available",
                  &infer::InferenceRuntime::isDeviceAvailable)
      // Takes the input spec as the same camelCase dict the API layer already
      // builds from `InputSpec.model_dump(by_alias=True)`, so no schema needs
      // duplicating on the C++ side.
      .def(
          "load_model_bytes",
          [](infer::InferenceRuntime &self, py::bytes artifact,
             const py::dict &inputSpec) {
            const std::string data = artifact;
            const auto spec = inputSpecFromDict(inputSpec);
            py::gil_scoped_release release;
            self.loadModelBytes(
                std::span<const std::byte>(
                    reinterpret_cast<const std::byte *>(data.data()),
                    data.size()),
                spec);
          },
          py::arg("artifact"), py::arg("input_spec"))
      .def("dry_run", &infer::InferenceRuntime::dryRun,
           py::call_guard<py::gil_scoped_release>())
      // Returns (output volume, provenance dict) rather than taking a
      // provenance out-param: Python has no clean equivalent of a mutable
      // reference into a freshly-constructed value.
      .def(
          "run",
          [](infer::InferenceRuntime &self, const py::dict &inputSpec,
             py::bytes modelSha256, const volume::Volume &input) {
            infer::ModelDescriptor descriptor;
            descriptor.inputSpec = inputSpecFromDict(inputSpec);
            descriptor.sha256 = sha256ArrayFromBytes(modelSha256);

            infer::RunProvenance provenance;
            volume::Volume output = [&] {
              py::gil_scoped_release release;
              return self.run(descriptor, input, provenance);
            }();

            py::dict provenanceDict;
            provenanceDict["input_sha256"] = py::bytes(
                reinterpret_cast<const char *>(provenance.inputSha256.data()),
                provenance.inputSha256.size());
            provenanceDict["model_sha256"] = py::bytes(
                reinterpret_cast<const char *>(provenance.modelSha256.data()),
                provenance.modelSha256.size());
            provenanceDict["engine_cache_key"] = provenance.engineCacheKey;
            provenanceDict["gpu_name"] = provenance.gpuName;
            provenanceDict["driver_version"] = provenance.driverVersion;
            provenanceDict["runtime_version"] = provenance.runtimeVersion;
            provenanceDict["duration_us"] = provenance.durationUs;

            return py::make_tuple(std::move(output), provenanceDict);
          },
          py::arg("input_spec"), py::arg("model_sha256"), py::arg("input"));
}
