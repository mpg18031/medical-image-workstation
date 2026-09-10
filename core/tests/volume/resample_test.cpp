#include <gtest/gtest.h>

#include <cmath>

#include "mivw/volume/volume.hpp"

namespace {

using namespace mivw::volume;

Volume makeVolume(Dims3 dims, Vec3 spacing) {
    Volume v{dims, spacing, DType::Int16};
    auto bytes = v.bytes();
    auto* voxels = reinterpret_cast<std::int16_t*>(bytes.data());
    for (std::size_t i = 0; i < v.voxelCount(); ++i) {
        voxels[i] = static_cast<std::int16_t>(i % 1024);
    }
    return v;
}

TEST(Resample, PreservesPhysicalExtentWithinHalfVoxel) {
    // Typical clinical CT: fine in-plane, coarse through-plane.
    const auto src = makeVolume({256, 256, 120}, {0.7, 0.7, 3.0});
    const auto dst = resampleIsotropic(src, 1.0);

    for (int axis = 0; axis < 3; ++axis) {
        const double srcExtent =
            static_cast<double>(src.dims()[axis]) * src.spacing()[axis];
        const double dstExtent =
            static_cast<double>(dst.dims()[axis]) * dst.spacing()[axis];
        EXPECT_NEAR(srcExtent, dstExtent, 0.5) << "axis " << axis;
    }
}

TEST(Resample, ProducesIsotropicSpacing) {
    const auto dst = resampleIsotropic(makeVolume({64, 64, 32}, {0.5, 0.5, 2.0}), 1.0);
    EXPECT_DOUBLE_EQ(dst.spacing()[0], 1.0);
    EXPECT_DOUBLE_EQ(dst.spacing()[1], 1.0);
    EXPECT_DOUBLE_EQ(dst.spacing()[2], 1.0);
}

TEST(Resample, PreservesOriginSoAnnotationsStayValid) {
    auto src = makeVolume({32, 32, 32}, {1.0, 1.0, 1.0});
    src.setOrigin({-120.5, 43.25, 900.0});
    const auto dst = resampleIsotropic(src, 0.5);

    EXPECT_DOUBLE_EQ(dst.origin()[0], src.origin()[0]);
    EXPECT_DOUBLE_EQ(dst.origin()[1], src.origin()[1]);
    EXPECT_DOUBLE_EQ(dst.origin()[2], src.origin()[2]);
}

TEST(CoordinateTransform, RoundTripsThroughPatientSpace) {
    auto v = makeVolume({64, 64, 64}, {0.8, 0.8, 1.25});
    v.setOrigin({10.0, -20.0, 30.0});

    const Vec3 voxel{12.5, 33.0, 7.25};
    const Vec3 patient = v.voxelToPatient(voxel);
    const Vec3 back = v.patientToVoxel(patient);

    for (int i = 0; i < 3; ++i) {
        EXPECT_NEAR(voxel[i], back[i], 1e-9) << "component " << i;
    }
}

TEST(ApplyRescale, ConvertsStoredValuesToHounsfieldUnits) {
    Volume v{{2, 1, 1}, {1.0, 1.0, 1.0}, DType::Int16};
    auto* voxels = reinterpret_cast<std::int16_t*>(v.bytes().data());
    voxels[0] = 0;
    voxels[1] = 1000;

    const auto hu = applyRescale(v, 1.0, -1024.0);
    const auto* out = reinterpret_cast<const float*>(hu.bytes().data());

    EXPECT_FLOAT_EQ(out[0], -1024.0F);  // air
    EXPECT_FLOAT_EQ(out[1], -24.0F);
}

TEST(Volume, RejectsSingularDirectionMatrix) {
    Volume v{{4, 4, 4}, {1.0, 1.0, 1.0}, DType::Int16};
    v.setDirection({0, 0, 0, 0, 0, 0, 0, 0, 0});  // corrupt DICOM geometry
    EXPECT_THROW((void)v.patientToVoxel({0.0, 0.0, 0.0}), std::invalid_argument);
}

}  // namespace
