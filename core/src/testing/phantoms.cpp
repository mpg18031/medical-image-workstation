#include "mivw/testing/phantoms.hpp"

#include "mivw/util/sha256.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>

namespace mivw::testing {

namespace {

constexpr double kAirHu = -1000.0;
constexpr double kTissueHu = 300.0;

std::size_t linearIndex(const Dims3 &dims, std::int32_t x, std::int32_t y,
                        std::int32_t z) {
  return (static_cast<std::size_t>(z) * static_cast<std::size_t>(dims[1]) +
          static_cast<std::size_t>(y)) *
             static_cast<std::size_t>(dims[0]) +
         static_cast<std::size_t>(x);
}

/// Normalised coordinate in [-1, 1] at the centre of a voxel.
double normalised(std::int32_t i, std::int32_t n) {
  return (static_cast<double>(i) + 0.5) / static_cast<double>(n) * 2.0 - 1.0;
}

Volume fill(Dims3 dims, Vec3 spacing, const auto &valueAt) {
  Volume v{dims, spacing, volume::DType::Int16};
  auto *voxels = reinterpret_cast<std::int16_t *>(v.bytes().data());

  for (std::int32_t z = 0; z < dims[2]; ++z) {
    for (std::int32_t y = 0; y < dims[1]; ++y) {
      for (std::int32_t x = 0; x < dims[0]; ++x) {
        const double value =
            valueAt(normalised(x, dims[0]), normalised(y, dims[1]),
                    normalised(z, dims[2]));
        voxels[linearIndex(dims, x, y, z)] = static_cast<std::int16_t>(
            std::clamp(std::lround(value), -32768L, 32767L));
      }
    }
  }
  return v;
}

} // namespace

Volume makeSpherePhantom(Dims3 dims, Vec3 spacingMm) {
  constexpr double kRadius = 0.6;
  return fill(dims, spacingMm, [](double x, double y, double z) {
    return (x * x + y * y + z * z) <= kRadius * kRadius ? kTissueHu : kAirHu;
  });
}

Volume makeSphereMask(Dims3 dims, Vec3 spacingMm) {
  constexpr double kRadius = 0.6;
  return fill(dims, spacingMm, [](double x, double y, double z) {
    return (x * x + y * y + z * z) <= kRadius * kRadius ? 1.0 : 0.0;
  });
}

Volume makeShepLoganPhantom(Dims3 dims, Vec3 spacingMm) {
  struct Ellipsoid {
    double intensity;
    Vec3 centre;
    Vec3 radii;
  };

  static constexpr std::array<Ellipsoid, 6> kEllipsoids{{
      {1.0, {0.0, 0.0, 0.0}, {0.69, 0.92, 0.9}},
      {-0.8, {0.0, -0.0184, 0.0}, {0.6624, 0.874, 0.88}},
      {-0.2, {0.22, 0.0, 0.0}, {0.11, 0.16, 0.21}},
      {-0.2, {-0.22, 0.0, 0.0}, {0.11, 0.16, 0.22}},
      {0.1, {0.0, 0.35, 0.0}, {0.21, 0.25, 0.5}},
      {0.1, {0.0, 0.1, 0.0}, {0.046, 0.046, 0.046}},
  }};

  return fill(dims, spacingMm, [](double x, double y, double z) {
    double accum = 0.0;
    for (const auto &e : kEllipsoids) {
      const double dx = (x - e.centre[0]) / e.radii[0];
      const double dy = (y - e.centre[1]) / e.radii[1];
      const double dz = (z - e.centre[2]) / e.radii[2];
      if (dx * dx + dy * dy + dz * dz <= 1.0) {
        accum += e.intensity;
      }
    }
    return accum * 1000.0 - 1000.0;
  });
}

Volume makeLinearRamp(Dims3 dims, Vec3 coefficients) {
  Volume v{dims, {1.0, 1.0, 1.0}, volume::DType::Float32};
  auto *voxels = reinterpret_cast<float *>(v.bytes().data());

  for (std::int32_t z = 0; z < dims[2]; ++z) {
    for (std::int32_t y = 0; y < dims[1]; ++y) {
      for (std::int32_t x = 0; x < dims[0]; ++x) {
        voxels[linearIndex(dims, x, y, z)] = static_cast<float>(
            coefficients[0] * x + coefficients[1] * y + coefficients[2] * z);
      }
    }
  }
  return v;
}

std::vector<std::array<float, 4>> labelPalette(int labelCount) {
  std::vector<std::array<float, 4>> palette;
  palette.reserve(static_cast<std::size_t>(labelCount));

  // Index 0 is background and must be fully transparent, otherwise the
  // overlay hides the volume it is meant to annotate.
  palette.push_back({0.0F, 0.0F, 0.0F, 0.0F});

  // Golden-angle hue rotation keeps adjacent labels visually distinct.
  constexpr double kGoldenAngle = 137.507764;
  for (int i = 1; i < labelCount; ++i) {
    const double hue = std::fmod(kGoldenAngle * i, 360.0) / 60.0;
    const double f = hue - std::floor(hue);
    const auto sector = static_cast<int>(hue) % 6;

    const float p = 0.0F;
    const auto q = static_cast<float>(1.0 - f);
    const auto t = static_cast<float>(f);

    switch (sector) {
    case 0:
      palette.push_back({1.0F, t, p, 1.0F});
      break;
    case 1:
      palette.push_back({q, 1.0F, p, 1.0F});
      break;
    case 2:
      palette.push_back({p, 1.0F, t, 1.0F});
      break;
    case 3:
      palette.push_back({p, q, 1.0F, 1.0F});
      break;
    case 4:
      palette.push_back({t, p, 1.0F, 1.0F});
      break;
    default:
      palette.push_back({1.0F, p, q, 1.0F});
      break;
    }
  }
  return palette;
}

std::filesystem::path fixturePath(const std::string &relative) {
  return std::filesystem::path{MIVW_FIXTURE_DIR} / relative;
}

std::array<std::uint8_t, 32> sha256OfFile(const std::filesystem::path &path) {
  return util::sha256File(path);
}

std::array<std::uint8_t, 32> sha256OfVolume(const Volume &volume) {
  return util::sha256(volume.bytes());
}

} // namespace mivw::testing
