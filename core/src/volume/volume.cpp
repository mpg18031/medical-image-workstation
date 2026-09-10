#include "mivw/volume/volume.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace mivw::volume {

namespace {

std::size_t bytesPerVoxel(DType dtype) noexcept {
  switch (dtype) {
  case DType::Int16:
  case DType::UInt16:
    return 2;
  case DType::Float32:
    return 4;
  }
  return 2;
}

double readVoxel(const Volume &v, std::int32_t x, std::int32_t y,
                 std::int32_t z) {
  const auto &dims = v.dims();
  x = std::clamp(x, 0, dims[0] - 1);
  y = std::clamp(y, 0, dims[1] - 1);
  z = std::clamp(z, 0, dims[2] - 1);

  const std::size_t index =
      (static_cast<std::size_t>(z) * static_cast<std::size_t>(dims[1]) +
       static_cast<std::size_t>(y)) *
          static_cast<std::size_t>(dims[0]) +
      static_cast<std::size_t>(x);

  const auto bytes = v.bytes();
  switch (v.dtype()) {
  case DType::Int16:
    return static_cast<double>(
        reinterpret_cast<const std::int16_t *>(bytes.data())[index]);
  case DType::UInt16:
    return static_cast<double>(
        reinterpret_cast<const std::uint16_t *>(bytes.data())[index]);
  case DType::Float32:
    return static_cast<double>(
        reinterpret_cast<const float *>(bytes.data())[index]);
  }
  return 0.0;
}

double sampleTrilinear(const Volume &v, double x, double y, double z) {
  const auto x0 = static_cast<std::int32_t>(std::floor(x));
  const auto y0 = static_cast<std::int32_t>(std::floor(y));
  const auto z0 = static_cast<std::int32_t>(std::floor(z));

  const double fx = x - x0;
  const double fy = y - y0;
  const double fz = z - z0;

  const double c000 = readVoxel(v, x0, y0, z0);
  const double c100 = readVoxel(v, x0 + 1, y0, z0);
  const double c010 = readVoxel(v, x0, y0 + 1, z0);
  const double c110 = readVoxel(v, x0 + 1, y0 + 1, z0);
  const double c001 = readVoxel(v, x0, y0, z0 + 1);
  const double c101 = readVoxel(v, x0 + 1, y0, z0 + 1);
  const double c011 = readVoxel(v, x0, y0 + 1, z0 + 1);
  const double c111 = readVoxel(v, x0 + 1, y0 + 1, z0 + 1);

  const double c00 = c000 * (1 - fx) + c100 * fx;
  const double c10 = c010 * (1 - fx) + c110 * fx;
  const double c01 = c001 * (1 - fx) + c101 * fx;
  const double c11 = c011 * (1 - fx) + c111 * fx;

  return (c00 * (1 - fy) + c10 * fy) * (1 - fz) +
         (c01 * (1 - fy) + c11 * fy) * fz;
}

void writeVoxel(Volume &v, std::size_t index, double value) {
  auto bytes = v.bytes();
  switch (v.dtype()) {
  case DType::Int16:
    reinterpret_cast<std::int16_t *>(bytes.data())[index] =
        static_cast<std::int16_t>(std::lround(value));
    break;
  case DType::UInt16:
    reinterpret_cast<std::uint16_t *>(bytes.data())[index] =
        static_cast<std::uint16_t>(std::lround(std::max(0.0, value)));
    break;
  case DType::Float32:
    reinterpret_cast<float *>(bytes.data())[index] = static_cast<float>(value);
    break;
  }
}

} // namespace

Volume::Volume(Dims3 dims, Vec3 spacingMm, DType dtype)
    : dims_{dims}, spacingMm_{spacingMm}, dtype_{dtype} {
  if (dims[0] <= 0 || dims[1] <= 0 || dims[2] <= 0) {
    throw std::invalid_argument("volume dimensions must be positive");
  }
  if (spacingMm[0] <= 0.0 || spacingMm[1] <= 0.0 || spacingMm[2] <= 0.0) {
    throw std::invalid_argument("voxel spacing must be positive");
  }
  data_.assign(sizeBytes(), std::byte{0});
}

std::size_t Volume::voxelCount() const noexcept {
  return static_cast<std::size_t>(dims_[0]) *
         static_cast<std::size_t>(dims_[1]) *
         static_cast<std::size_t>(dims_[2]);
}

std::size_t Volume::sizeBytes() const noexcept {
  return voxelCount() * bytesPerVoxel(dtype_);
}

std::span<std::byte> Volume::bytes() noexcept {
  return {data_.data(), data_.size()};
}

std::span<const std::byte> Volume::bytes() const noexcept {
  return {data_.data(), data_.size()};
}

Vec3 Volume::voxelToPatient(Vec3 voxel) const noexcept {
  const Vec3 scaled{voxel[0] * spacingMm_[0], voxel[1] * spacingMm_[1],
                    voxel[2] * spacingMm_[2]};
  return {
      originMm_[0] + direction_[0] * scaled[0] + direction_[1] * scaled[1] +
          direction_[2] * scaled[2],
      originMm_[1] + direction_[3] * scaled[0] + direction_[4] * scaled[1] +
          direction_[5] * scaled[2],
      originMm_[2] + direction_[6] * scaled[0] + direction_[7] * scaled[1] +
          direction_[8] * scaled[2],
  };
}

Vec3 Volume::patientToVoxel(Vec3 patientMm) const {
  const auto &m = direction_;
  const double det = m[0] * (m[4] * m[8] - m[5] * m[7]) -
                     m[1] * (m[3] * m[8] - m[5] * m[6]) +
                     m[2] * (m[3] * m[7] - m[4] * m[6]);

  // A singular direction matrix means the DICOM geometry is corrupt; failing
  // here is far better than silently producing nonsense coordinates.
  if (std::abs(det) < 1e-12) {
    throw std::invalid_argument("direction matrix is singular");
  }

  const double inv = 1.0 / det;
  const std::array<double, 9> adj{
      (m[4] * m[8] - m[5] * m[7]) * inv, (m[2] * m[7] - m[1] * m[8]) * inv,
      (m[1] * m[5] - m[2] * m[4]) * inv, (m[5] * m[6] - m[3] * m[8]) * inv,
      (m[0] * m[8] - m[2] * m[6]) * inv, (m[2] * m[3] - m[0] * m[5]) * inv,
      (m[3] * m[7] - m[4] * m[6]) * inv, (m[1] * m[6] - m[0] * m[7]) * inv,
      (m[0] * m[4] - m[1] * m[3]) * inv,
  };

  const Vec3 d{patientMm[0] - originMm_[0], patientMm[1] - originMm_[1],
               patientMm[2] - originMm_[2]};

  return {
      (adj[0] * d[0] + adj[1] * d[1] + adj[2] * d[2]) / spacingMm_[0],
      (adj[3] * d[0] + adj[4] * d[1] + adj[5] * d[2]) / spacingMm_[1],
      (adj[6] * d[0] + adj[7] * d[1] + adj[8] * d[2]) / spacingMm_[2],
  };
}

Volume Volume::clone() const {
  Volume copy{dims_, spacingMm_, dtype_};
  copy.originMm_ = originMm_;
  copy.direction_ = direction_;
  std::memcpy(copy.data_.data(), data_.data(), data_.size());
  return copy;
}

Volume resampleIsotropic(const Volume &src, double targetSpacingMm) {
  if (targetSpacingMm <= 0.0) {
    throw std::invalid_argument("target spacing must be positive");
  }

  const auto &srcDims = src.dims();
  const auto &srcSpacing = src.spacing();

  // Round so the physical extent is preserved to within half a voxel, which
  // is the invariant the test suite asserts.
  Dims3 dstDims{};
  for (int axis = 0; axis < 3; ++axis) {
    const double extent = static_cast<double>(srcDims[axis]) * srcSpacing[axis];
    dstDims[axis] = std::max(
        1, static_cast<std::int32_t>(std::llround(extent / targetSpacingMm)));
  }

  Volume dst{dstDims,
             {targetSpacingMm, targetSpacingMm, targetSpacingMm},
             src.dtype()};
  dst.setOrigin(src.origin());
  dst.setDirection(src.direction());

  for (std::int32_t z = 0; z < dstDims[2]; ++z) {
    for (std::int32_t y = 0; y < dstDims[1]; ++y) {
      for (std::int32_t x = 0; x < dstDims[0]; ++x) {
        const double sx = (x + 0.5) * targetSpacingMm / srcSpacing[0] - 0.5;
        const double sy = (y + 0.5) * targetSpacingMm / srcSpacing[1] - 0.5;
        const double sz = (z + 0.5) * targetSpacingMm / srcSpacing[2] - 0.5;

        const std::size_t index = (static_cast<std::size_t>(z) *
                                       static_cast<std::size_t>(dstDims[1]) +
                                   static_cast<std::size_t>(y)) *
                                      static_cast<std::size_t>(dstDims[0]) +
                                  static_cast<std::size_t>(x);

        writeVoxel(dst, index, sampleTrilinear(src, sx, sy, sz));
      }
    }
  }

  return dst;
}

Volume applyRescale(const Volume &src, double slope, double intercept) {
  // Output is float32: Hounsfield units after rescale routinely fall outside
  // the source integer range.
  Volume dst{src.dims(), src.spacing(), DType::Float32};
  dst.setOrigin(src.origin());
  dst.setDirection(src.direction());

  auto out = reinterpret_cast<float *>(dst.bytes().data());
  const auto &dims = src.dims();

  std::size_t index = 0;
  for (std::int32_t z = 0; z < dims[2]; ++z) {
    for (std::int32_t y = 0; y < dims[1]; ++y) {
      for (std::int32_t x = 0; x < dims[0]; ++x, ++index) {
        out[index] =
            static_cast<float>(readVoxel(src, x, y, z) * slope + intercept);
      }
    }
  }

  return dst;
}

} // namespace mivw::volume
