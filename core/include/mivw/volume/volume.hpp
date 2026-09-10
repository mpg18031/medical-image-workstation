#pragma once

#include <array>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <vector>

namespace mivw::volume {

enum class DType : std::uint8_t { Int16, UInt16, Float32 };

using Dims3    = std::array<std::int32_t, 3>;
using Vec3     = std::array<double, 3>;
using Matrix3  = std::array<double, 9>;  ///< Row-major direction cosines.

/// A dense 3D voxel buffer with the physical geometry needed to place it in
/// patient space.
///
/// Move-only by design: a 512^3 int16 volume is 256 MB, so an implicit copy is
/// always a bug rather than a convenience.
class Volume {
public:
    Volume(Dims3 dims, Vec3 spacingMm, DType dtype);

    Volume(const Volume&)            = delete;
    Volume& operator=(const Volume&) = delete;
    Volume(Volume&&) noexcept        = default;
    Volume& operator=(Volume&&) noexcept = default;
    ~Volume()                        = default;

    [[nodiscard]] const Dims3&   dims()      const noexcept { return dims_; }
    [[nodiscard]] const Vec3&    spacing()   const noexcept { return spacingMm_; }
    [[nodiscard]] const Vec3&    origin()    const noexcept { return originMm_; }
    [[nodiscard]] const Matrix3& direction() const noexcept { return direction_; }
    [[nodiscard]] DType          dtype()     const noexcept { return dtype_; }

    [[nodiscard]] std::size_t voxelCount() const noexcept;
    [[nodiscard]] std::size_t sizeBytes()  const noexcept;

    [[nodiscard]] std::span<std::byte>       bytes()       noexcept;
    [[nodiscard]] std::span<const std::byte> bytes() const noexcept;

    void setOrigin(Vec3 originMm) noexcept { originMm_ = originMm; }
    void setDirection(Matrix3 direction) noexcept { direction_ = direction; }

    /// Voxel index -> patient coordinates in millimetres.
    [[nodiscard]] Vec3 voxelToPatient(Vec3 voxel) const noexcept;

    /// Patient millimetres -> continuous voxel index. Throws if the direction
    /// matrix is singular, which indicates corrupt DICOM geometry.
    [[nodiscard]] Vec3 patientToVoxel(Vec3 patientMm) const;

    /// Deliberately explicit, so a copy is always visible at the call site.
    [[nodiscard]] Volume clone() const;

private:
    Dims3   dims_{};
    Vec3    spacingMm_{1.0, 1.0, 1.0};
    Vec3    originMm_{0.0, 0.0, 0.0};
    Matrix3 direction_{1, 0, 0, 0, 1, 0, 0, 0, 1};
    DType   dtype_{DType::Int16};
    std::vector<std::byte> data_;
};

/// Resample to isotropic spacing. Physical extent is preserved to within half a
/// voxel on every axis; this invariant is asserted by the test suite.
[[nodiscard]] Volume resampleIsotropic(const Volume& src, double targetSpacingMm);

/// Apply DICOM RescaleSlope/RescaleIntercept to obtain Hounsfield units.
[[nodiscard]] Volume applyRescale(const Volume& src, double slope, double intercept);

}  // namespace mivw::volume
