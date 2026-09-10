#pragma once

// Deterministic volumes for tests. Nothing here derives from patient data.

#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

#include "mivw/volume/volume.hpp"

namespace mivw::testing {

using volume::Dims3;
using volume::Vec3;
using volume::Volume;

/// Solid sphere: 300 HU inside, -1000 HU (air) outside.
[[nodiscard]] Volume makeSpherePhantom(Dims3 dims,
                                       Vec3 spacingMm = {1.0, 1.0, 1.0});

/// Binary label mask matching `makeSpherePhantom` at the same dimensions.
[[nodiscard]] Volume makeSphereMask(Dims3 dims,
                                    Vec3 spacingMm = {1.0, 1.0, 1.0});

/// 3D Shepp-Logan, scaled into a plausible Hounsfield range.
[[nodiscard]] Volume makeShepLoganPhantom(Dims3 dims,
                                          Vec3 spacingMm = {1.0, 1.0, 1.0});

/// Linear ramp f(x,y,z) = ax + by + cz, so the analytic gradient is constant.
[[nodiscard]] Volume makeLinearRamp(Dims3 dims, Vec3 coefficients);

/// Distinct RGBA colours for label indices, index 0 always fully transparent.
[[nodiscard]] std::vector<std::array<float, 4>> labelPalette(int labelCount);

[[nodiscard]] std::filesystem::path fixturePath(const std::string &relative);

[[nodiscard]] std::array<std::uint8_t, 32>
sha256OfFile(const std::filesystem::path &path);
[[nodiscard]] std::array<std::uint8_t, 32> sha256OfVolume(const Volume &volume);

} // namespace mivw::testing
