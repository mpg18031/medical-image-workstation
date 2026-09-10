// GPU kernel correctness, checked against a CPU reference implementation.
// Labelled "cuda" in CTest so runners without a device skip rather than fail.

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <numeric>
#include <vector>

#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/kernels.hpp"
#include "mivw/cuda/stream.hpp"

namespace {

using namespace mivw::cuda;

constexpr float kTolerance = 1e-5F;

std::vector<float> windowReference(const std::vector<std::int16_t> &input,
                                   float center, float width) {
  const float lo = center - 0.5F * width;
  std::vector<float> out(input.size());
  std::transform(input.begin(), input.end(), out.begin(), [&](std::int16_t v) {
    return std::clamp((static_cast<float>(v) - lo) / width, 0.0F, 1.0F);
  });
  return out;
}

class WindowKernelTest : public ::testing::Test {
protected:
  void SetUp() override {
    if (!isDeviceAvailable()) {
      GTEST_SKIP() << "no CUDA device on this runner";
    }
  }

  Stream stream;
};

TEST_F(WindowKernelTest, MatchesTheCpuReference) {
  std::vector<std::int16_t> host(1 << 16);
  for (std::size_t i = 0; i < host.size(); ++i) {
    host[i] = static_cast<std::int16_t>(static_cast<int>(i % 4096) - 2048);
  }

  DeviceBuffer<std::int16_t> input(host.size());
  DeviceBuffer<float> output(host.size());
  input.copyFromHost(host, stream);

  launchWindowLevel(input, output, /*center=*/40.0F, /*width=*/400.0F, stream);

  const auto actual = output.copyToHost(stream);
  stream.synchronise();

  const auto expected = windowReference(host, 40.0F, 400.0F);
  ASSERT_EQ(actual.size(), expected.size());
  for (std::size_t i = 0; i < actual.size(); ++i) {
    ASSERT_NEAR(actual[i], expected[i], kTolerance) << "index " << i;
  }
}

TEST_F(WindowKernelTest, ClampsBelowAndAboveTheWindow) {
  const std::vector<std::int16_t> host{-32000, -160, 40, 240, 32000};

  DeviceBuffer<std::int16_t> input(host.size());
  DeviceBuffer<float> output(host.size());
  input.copyFromHost(host, stream);

  launchWindowLevel(input, output, 40.0F, 400.0F, stream);
  const auto actual = output.copyToHost(stream);
  stream.synchronise();

  EXPECT_FLOAT_EQ(actual.front(), 0.0F);
  EXPECT_FLOAT_EQ(actual.back(), 1.0F);
  EXPECT_NEAR(actual[2], 0.5F, kTolerance); // window centre
  for (float v : actual) {
    EXPECT_GE(v, 0.0F);
    EXPECT_LE(v, 1.0F);
  }
}

TEST_F(WindowKernelTest, HandlesSizesThatAreNotMultiplesOfTheBlockSize) {
  // Off-by-one in the bounds guard only shows up on ragged sizes.
  for (std::size_t n : {1U, 31U, 33U, 255U, 257U, 1023U, 1025U}) {
    std::vector<std::int16_t> host(n, 100);
    DeviceBuffer<std::int16_t> input(n);
    DeviceBuffer<float> output(n);
    input.copyFromHost(host, stream);

    launchWindowLevel(input, output, 40.0F, 400.0F, stream);
    const auto actual = output.copyToHost(stream);
    stream.synchronise();

    ASSERT_EQ(actual.size(), n);
    for (float v : actual) {
      ASSERT_NEAR(v, windowReference(host, 40.0F, 400.0F)[0], kTolerance)
          << "n = " << n;
    }
  }
}

TEST_F(WindowKernelTest, RejectsNonPositiveWidthInsteadOfDividingByZero) {
  DeviceBuffer<std::int16_t> input(16);
  DeviceBuffer<float> output(16);
  EXPECT_THROW(launchWindowLevel(input, output, 40.0F, 0.0F, stream),
               std::invalid_argument);
  EXPECT_THROW(launchWindowLevel(input, output, 40.0F, -100.0F, stream),
               std::invalid_argument);
}

TEST_F(WindowKernelTest, ProducesTheSameResultOnRepeatedLaunches) {
  std::vector<std::int16_t> host(4096);
  std::iota(host.begin(), host.end(), static_cast<std::int16_t>(-2048));

  DeviceBuffer<std::int16_t> input(host.size());
  DeviceBuffer<float> first(host.size());
  DeviceBuffer<float> second(host.size());
  input.copyFromHost(host, stream);

  launchWindowLevel(input, first, 40.0F, 400.0F, stream);
  launchWindowLevel(input, second, 40.0F, 400.0F, stream);

  const auto a = first.copyToHost(stream);
  const auto b = second.copyToHost(stream);
  stream.synchronise();

  EXPECT_EQ(a, b);
}

TEST_F(WindowKernelTest, DeviceBufferFreesOnScopeExit) {
  const std::size_t before = freeDeviceMemoryBytes();
  {
    DeviceBuffer<float> scoped(1 << 22);
    EXPECT_LT(freeDeviceMemoryBytes(), before);
  }
  // RAII, not manual cudaFree: allocation must not survive the scope.
  EXPECT_NEAR(static_cast<double>(freeDeviceMemoryBytes()),
              static_cast<double>(before), static_cast<double>(before) * 0.01);
}

} // namespace
