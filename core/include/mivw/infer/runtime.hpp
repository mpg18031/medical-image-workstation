#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include "mivw/volume/volume.hpp"

namespace mivw::infer {

class SpecMismatchError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

class DigestMismatchError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

enum class OutputKind : std::uint8_t {
  Segmentation,
  Classification,
  Heatmap,
  Landmarks
};

enum class Normalisation : std::uint8_t { None, ZScore, MinMax };

/// The input contract a registered model declares. Volumes are checked against
/// it and rejected on mismatch rather than silently adapted (see ADR 0005): a
/// plausible-looking wrong result is worse than a loud failure.
struct InputSpec {
  std::vector<std::int64_t> shape;
  volume::Vec3 spacingMm{1.0, 1.0, 1.0};
  std::string orientation{"RAS"};
  Normalisation normalisation{Normalisation::ZScore};
  std::array<float, 2> clipHu{-1000.0F, 1000.0F};
  double spacingToleranceMm{0.01};
};

struct ModelDescriptor {
  std::string name;
  std::string version;
  std::filesystem::path artifactPath;
  std::array<std::uint8_t, 32> sha256{};
  OutputKind outputKind{OutputKind::Segmentation};
  InputSpec inputSpec;
};

struct RunProvenance {
  std::array<std::uint8_t, 32> inputSha256{};
  std::array<std::uint8_t, 32> modelSha256{};
  std::string engineCacheKey;
  std::string gpuName;
  std::string driverVersion;
  std::string runtimeVersion;
  std::uint64_t durationUs{0};
};

/// ONNX Runtime wrapper with a TensorRT execution provider.
///
/// Engines are cached per (model digest, GPU architecture, TensorRT version);
/// a miss triggers a rebuild rather than a silent fallback to a stale engine.
class InferenceRuntime {
public:
  [[nodiscard]] static bool isDeviceAvailable() noexcept;

  /// Engines are cached per (model digest, GPU architecture, TensorRT
  /// version). Omitting the versions would let a stale engine survive a
  /// toolkit upgrade, which is a correctness hazard rather than a slowdown.
  [[nodiscard]] static std::string
  engineCacheKey(const std::array<std::uint8_t, 32> &modelDigest,
                 const std::string &gpuArch,
                 const std::string &tensorRtVersion);

  InferenceRuntime();
  ~InferenceRuntime();

  InferenceRuntime(const InferenceRuntime &) = delete;
  InferenceRuntime &operator=(const InferenceRuntime &) = delete;

  /// Verifies the artefact digest before loading. Throws DigestMismatchError
  /// if the file on disk does not match the registry entry.
  void loadModel(const ModelDescriptor &descriptor);

  /// Loads from memory, for registration-time validation where the artefact
  /// has been fetched but not yet written to disk.
  void loadModelBytes(std::span<const std::byte> artifact,
                      const InputSpec &spec);

  /// Synthetic-input inference, so a broken model is discovered at
  /// registration rather than at clinical use.
  void dryRun();

  /// Throws SpecMismatchError when the volume violates the declared spec.
  void validateInput(const ModelDescriptor &descriptor,
                     const volume::Volume &input) const;

  /// Sliding-window inference for volumes larger than the model's patch size.
  [[nodiscard]] volume::Volume run(const ModelDescriptor &descriptor,
                                   const volume::Volume &input,
                                   RunProvenance &provenanceOut);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace mivw::infer
