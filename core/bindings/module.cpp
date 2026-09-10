#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>

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
      // policy prevents the volume outliving the array.
      .def(
          "as_array",
          [](volume::Volume &self) {
            const auto &d = self.dims();
            return py::array_t<std::int16_t>(
                {d[2], d[1], d[0]},
                reinterpret_cast<std::int16_t *>(self.bytes().data()),
                py::cast(self));
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
}
