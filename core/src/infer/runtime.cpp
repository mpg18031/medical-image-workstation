#include "mivw/infer/runtime.hpp"
#include "mivw/cuda/device_buffer.hpp"
#include "mivw/util/sha256.hpp"

#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <optional>
#include <sstream>
#include <vector>

namespace mivw::infer {

namespace {

std::vector<float> volumeToFloat(const volume::Volume &vol) {
  std::vector<float> out(vol.voxelCount());
  const auto bytes = vol.bytes();
  switch (vol.dtype()) {
  case volume::DType::Int16: {
    const auto *src = reinterpret_cast<const std::int16_t *>(bytes.data());
    for (std::size_t i = 0; i < out.size(); ++i)
      out[i] = static_cast<float>(src[i]);
    break;
  }
  case volume::DType::UInt16: {
    const auto *src = reinterpret_cast<const std::uint16_t *>(bytes.data());
    for (std::size_t i = 0; i < out.size(); ++i)
      out[i] = static_cast<float>(src[i]);
    break;
  }
  case volume::DType::Float32: {
    const auto *src = reinterpret_cast<const float *>(bytes.data());
    std::copy(src, src + out.size(), out.begin());
    break;
  }
  }
  return out;
}

} // namespace

struct InferenceRuntime::Impl {
  Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "mivw"};
  Ort::Session session{nullptr};
  bool hasSession{false};
};

bool InferenceRuntime::isDeviceAvailable() noexcept {
  return cuda::isDeviceAvailable();
}

std::string InferenceRuntime::engineCacheKey(
    const std::array<std::uint8_t, 32> &modelDigest, const std::string &gpuArch,
    const std::string &tensorRtVersion) {
  std::ostringstream oss;
  for (const auto byte : modelDigest) {
    oss << std::hex << std::setfill('0') << std::setw(2)
        << static_cast<int>(byte);
  }
  oss << '_' << gpuArch << '_' << tensorRtVersion;
  return oss.str();
}

InferenceRuntime::InferenceRuntime() : impl_{std::make_unique<Impl>()} {}
InferenceRuntime::~InferenceRuntime() = default;

void InferenceRuntime::loadModel(const ModelDescriptor &descriptor) {
  const auto actualDigest = util::sha256File(descriptor.artifactPath);
  if (actualDigest != descriptor.sha256) {
    throw DigestMismatchError(
        "model artefact digest does not match the registry entry: " +
        descriptor.artifactPath.string());
  }

  Ort::SessionOptions options;
  impl_->session =
      Ort::Session(impl_->env, descriptor.artifactPath.c_str(), options);
  impl_->hasSession = true;
}

void InferenceRuntime::loadModelBytes(std::span<const std::byte> artifact,
                                      const InputSpec &) {
  Ort::SessionOptions options;
  impl_->session =
      Ort::Session(impl_->env, artifact.data(), artifact.size(), options);
  impl_->hasSession = true;
}

void InferenceRuntime::dryRun() {
  if (!impl_->hasSession) {
    throw SpecMismatchError("dryRun called before a model was loaded");
  }
  Ort::AllocatorWithDefaultOptions allocator;
  auto inputName = impl_->session.GetInputNameAllocated(0, allocator);
  auto outputName = impl_->session.GetOutputNameAllocated(0, allocator);
  auto shape =
      impl_->session.GetInputTypeInfo(0).GetTensorTypeAndShapeInfo().GetShape();

  std::size_t count = 1;
  for (auto &dim : shape) {
    if (dim <= 0)
      dim = 1;
    count *= static_cast<std::size_t>(dim);
  }
  std::vector<float> zeros(count, 0.0F);

  const Ort::MemoryInfo memInfo =
      Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
  Ort::Value inputTensor = Ort::Value::CreateTensor<float>(
      memInfo, zeros.data(), zeros.size(), shape.data(), shape.size());

  const char *inputNames[] = {inputName.get()};
  const char *outputNames[] = {outputName.get()};
  impl_->session.Run(Ort::RunOptions{nullptr}, inputNames, &inputTensor, 1,
                     outputNames, 1);
}

void InferenceRuntime::validateInput(const ModelDescriptor &descriptor,
                                     const volume::Volume &input) const {
  const auto &spec = descriptor.inputSpec;
  if (spec.shape.size() != 5) {
    throw SpecMismatchError("model input spec must be 5-D (N,C,D,H,W)");
  }

  const auto dims = input.dims();
  const auto patchW = spec.shape[4];
  const auto patchH = spec.shape[3];
  const auto patchD = spec.shape[2];
  if (dims[0] < patchW || dims[1] < patchH || dims[2] < patchD) {
    std::ostringstream oss;
    oss << "volume (" << dims[0] << "x" << dims[1] << "x" << dims[2]
        << ") is smaller than the model's patch size (" << patchW << "x"
        << patchH << "x" << patchD << ")";
    throw SpecMismatchError(oss.str());
  }

  const auto spacing = input.spacing();
  for (int i = 0; i < 3; ++i) {
    if (std::abs(spacing[static_cast<std::size_t>(i)] -
                 spec.spacingMm[static_cast<std::size_t>(i)]) >
        spec.spacingToleranceMm) {
      std::ostringstream oss;
      oss << "spacing mismatch: expected " << spec.spacingMm[0] << ","
          << spec.spacingMm[1] << "," << spec.spacingMm[2] << " mm (tolerance "
          << spec.spacingToleranceMm << "), got " << spacing[0] << ","
          << spacing[1] << "," << spacing[2] << " mm";
      throw SpecMismatchError(oss.str());
    }
  }

  if (spec.orientation == "RAS") {
    static constexpr volume::Matrix3 kIdentity{1, 0, 0, 0, 1, 0, 0, 0, 1};
    const auto dir = input.direction();
    for (std::size_t i = 0; i < 9; ++i) {
      if (std::abs(dir[i] - kIdentity[i]) > 1e-6) {
        throw SpecMismatchError(
            "orientation mismatch: volume is not in RAS orientation");
      }
    }
  }
}

volume::Volume InferenceRuntime::run(const ModelDescriptor &descriptor,
                                     const volume::Volume &input,
                                     RunProvenance &provenanceOut) {
  validateInput(descriptor, input);
  if (!impl_->hasSession) {
    throw SpecMismatchError("run() called before a model was loaded");
  }

  const auto dims = input.dims();
  const std::vector<float> inputFloats = volumeToFloat(input);
  const std::array<std::int64_t, 5> shape{1, 1, dims[2], dims[1], dims[0]};

  const Ort::MemoryInfo memInfo =
      Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
  Ort::Value inputTensor = Ort::Value::CreateTensor<float>(
      memInfo, const_cast<float *>(inputFloats.data()), inputFloats.size(),
      shape.data(), shape.size());

  Ort::AllocatorWithDefaultOptions allocator;
  auto inputName = impl_->session.GetInputNameAllocated(0, allocator);
  auto outputName = impl_->session.GetOutputNameAllocated(0, allocator);
  const char *inputNames[] = {inputName.get()};
  const char *outputNames[] = {outputName.get()};

  const auto start = std::chrono::steady_clock::now();
  auto outputs = impl_->session.Run(Ort::RunOptions{nullptr}, inputNames,
                                    &inputTensor, 1, outputNames, 1);
  const auto end = std::chrono::steady_clock::now();

  const float *outData = outputs.front().GetTensorData<float>();
  volume::Volume result(dims, input.spacing(), volume::DType::Float32);
  auto *outBytes = reinterpret_cast<float *>(result.bytes().data());
  std::copy(outData, outData + result.voxelCount(), outBytes);
  result.setOrigin(input.origin());
  result.setDirection(input.direction());

  provenanceOut.inputSha256 = util::sha256(input.bytes());
  provenanceOut.modelSha256 = descriptor.sha256;
  provenanceOut.engineCacheKey =
      engineCacheKey(descriptor.sha256, "sm_generic", Ort::GetVersionString());
  provenanceOut.gpuName =
      cuda::isDeviceAvailable() ? cuda::deviceName() : "cpu";
  provenanceOut.driverVersion = cuda::driverVersion();
  provenanceOut.runtimeVersion = Ort::GetVersionString();
  provenanceOut.durationUs = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::microseconds>(end - start)
          .count());
  if (provenanceOut.durationUs == 0)
    provenanceOut.durationUs = 1;

  return result;
}

} // namespace mivw::infer
