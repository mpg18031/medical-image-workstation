// Central-difference gradient kernel, used for shading normals in the renderer.

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/kernels.hpp"
#include "mivw/cuda/stream.hpp"

namespace {

using namespace mivw::cuda;

constexpr int kDim = 32;
constexpr float kTolerance = 1e-4F;

std::size_t index(int x, int y, int z) {
    return static_cast<std::size_t>((z * kDim + y) * kDim + x);
}

/// f(x, y, z) = 2x + 3y - z, so the analytic gradient is constant (2, 3, -1).
std::vector<float> makeLinearRamp() {
    std::vector<float> v(static_cast<std::size_t>(kDim) * kDim * kDim);
    for (int z = 0; z < kDim; ++z) {
        for (int y = 0; y < kDim; ++y) {
            for (int x = 0; x < kDim; ++x) {
                v[index(x, y, z)] =
                    2.0F * static_cast<float>(x) + 3.0F * static_cast<float>(y) -
                    static_cast<float>(z);
            }
        }
    }
    return v;
}

class GradientKernelTest : public ::testing::Test {
protected:
    void SetUp() override {
        if (!isDeviceAvailable()) {
            GTEST_SKIP() << "no CUDA device on this runner";
        }
    }

    Stream stream;
};

TEST_F(GradientKernelTest, MatchesTheAnalyticGradientOfALinearField) {
    const auto host = makeLinearRamp();

    DeviceBuffer<float> input(host.size());
    DeviceBuffer<float3> output(host.size());
    input.copyFromHost(host, stream);

    launchGradient(input, output, {kDim, kDim, kDim}, {1.0F, 1.0F, 1.0F}, stream);
    const auto actual = output.copyToHost(stream);
    stream.synchronise();

    // Interior voxels only: boundaries use a one-sided difference.
    for (int z = 1; z < kDim - 1; ++z) {
        for (int y = 1; y < kDim - 1; ++y) {
            for (int x = 1; x < kDim - 1; ++x) {
                const auto g = actual[index(x, y, z)];
                ASSERT_NEAR(g.x, 2.0F, kTolerance);
                ASSERT_NEAR(g.y, 3.0F, kTolerance);
                ASSERT_NEAR(g.z, -1.0F, kTolerance);
            }
        }
    }
}

TEST_F(GradientKernelTest, ScalesWithVoxelSpacing) {
    const auto host = makeLinearRamp();

    DeviceBuffer<float> input(host.size());
    DeviceBuffer<float3> output(host.size());
    input.copyFromHost(host, stream);

    // Anisotropic spacing must be divided out, otherwise shading normals tilt
    // and the volume looks subtly wrong on clinical CT.
    launchGradient(input, output, {kDim, kDim, kDim}, {0.5F, 1.0F, 2.0F}, stream);
    const auto actual = output.copyToHost(stream);
    stream.synchronise();

    const auto g = actual[index(16, 16, 16)];
    EXPECT_NEAR(g.x, 2.0F / 0.5F, kTolerance);
    EXPECT_NEAR(g.y, 3.0F / 1.0F, kTolerance);
    EXPECT_NEAR(g.z, -1.0F / 2.0F, kTolerance);
}

TEST_F(GradientKernelTest, ReturnsZeroGradientForAConstantField) {
    const std::vector<float> host(static_cast<std::size_t>(kDim) * kDim * kDim, 42.0F);

    DeviceBuffer<float> input(host.size());
    DeviceBuffer<float3> output(host.size());
    input.copyFromHost(host, stream);

    launchGradient(input, output, {kDim, kDim, kDim}, {1.0F, 1.0F, 1.0F}, stream);
    const auto actual = output.copyToHost(stream);
    stream.synchronise();

    for (const auto& g : actual) {
        ASSERT_NEAR(std::sqrt(g.x * g.x + g.y * g.y + g.z * g.z), 0.0F, kTolerance);
    }
}

TEST_F(GradientKernelTest, DoesNotReadOutsideTheVolumeAtBoundaries) {
    // Correctness here is really an out-of-bounds check; run this suite under
    // compute-sanitizer in CI to make the assertion meaningful.
    const auto host = makeLinearRamp();

    DeviceBuffer<float> input(host.size());
    DeviceBuffer<float3> output(host.size());
    input.copyFromHost(host, stream);

    launchGradient(input, output, {kDim, kDim, kDim}, {1.0F, 1.0F, 1.0F}, stream);
    const auto actual = output.copyToHost(stream);
    stream.synchronise();

    for (const auto& g : actual) {
        ASSERT_TRUE(std::isfinite(g.x));
        ASSERT_TRUE(std::isfinite(g.y));
        ASSERT_TRUE(std::isfinite(g.z));
    }
}

TEST_F(GradientKernelTest, RejectsDimensionsThatDoNotMatchTheBuffer) {
    DeviceBuffer<float> input(64);
    DeviceBuffer<float3> output(64);
    EXPECT_THROW(
        launchGradient(input, output, {kDim, kDim, kDim}, {1.0F, 1.0F, 1.0F}, stream),
        std::invalid_argument);
}

}  // namespace
