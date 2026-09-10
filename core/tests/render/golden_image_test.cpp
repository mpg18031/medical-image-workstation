// Golden-image tests for the Vulkan renderer.
//
// Comparison is perceptual (SSIM), not exact: driver revisions legitimately
// change the last bit of a float, and an exact-match test would fail on every
// GPU upgrade while catching nothing real.

#include <gtest/gtest.h>

#include <filesystem>
#include <optional>

#include "mivw/render/renderer.hpp"
#include "mivw/testing/image_compare.hpp"
#include "mivw/testing/phantoms.hpp"

namespace {

using namespace mivw;

constexpr double kSsimThreshold = 0.995;

std::filesystem::path goldenPath(const std::string &name) {
  return std::filesystem::path{MIVW_FIXTURE_DIR} / "golden" / (name + ".png");
}

class GoldenImageTest : public ::testing::Test {
protected:
  void SetUp() override {
    if (!render::Renderer::isDeviceAvailable()) {
      GTEST_SKIP() << "no Vulkan device on this runner";
    }
    renderer_.emplace();
  }

  void expectMatchesGolden(const render::RenderParams &params,
                           const std::string &goldenName) {
    const auto frame = renderer_->render(params, /*sequence=*/1);
    const auto actual = mivw::testing::decodeFrame(frame);

    // MIVW_UPDATE_GOLDEN=1 regenerates baselines after an intentional
    // visual change. Never set in CI.
    if (std::getenv("MIVW_UPDATE_GOLDEN") != nullptr) {
      mivw::testing::writePng(goldenPath(goldenName), actual);
      GTEST_SKIP() << "golden image regenerated: " << goldenName;
    }

    const auto expected = mivw::testing::readPng(goldenPath(goldenName));
    ASSERT_EQ(actual.width, expected.width);
    ASSERT_EQ(actual.height, expected.height);

    const double ssim = mivw::testing::ssim(actual, expected);
    EXPECT_GE(ssim, kSsimThreshold)
        << "render diverged from " << goldenName << " (SSIM " << ssim << ")";

    if (ssim < kSsimThreshold) {
      mivw::testing::writePng(goldenPath(goldenName + ".actual"), actual);
    }
  }

  render::RenderParams stillParams() const {
    render::RenderParams params;
    params.quality = render::Quality::Still;
    params.width = 512;
    params.height = 512;
    return params;
  }

  std::optional<render::Renderer> renderer_;
};

TEST_F(GoldenImageTest, SpherePhantomFromFront) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  expectMatchesGolden(stillParams(), "sphere_front");
}

TEST_F(GoldenImageTest, SpherePhantomFromOblique) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));

  auto params = stillParams();
  params.camera.eye = {300.0F, 300.0F, -300.0F};
  expectMatchesGolden(params, "sphere_oblique");
}

TEST_F(GoldenImageTest, ShepLoganWithBoneWindow) {
  renderer_->setVolume(mivw::testing::makeShepLoganPhantom({256, 256, 128}));

  auto params = stillParams();
  params.window = {300.0F, 1500.0F};
  params.transferFunctionPreset = "ct-bone";
  expectMatchesGolden(params, "shepp_logan_bone");
}

TEST_F(GoldenImageTest, SegmentationOverlayCompositesAtRequestedOpacity) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  renderer_->setSegmentation(mivw::testing::makeSphereMask({128, 128, 128}),
                             mivw::testing::labelPalette(2));

  auto params = stillParams();
  params.segmentationVisible = true;
  params.segmentationOpacity = 0.45F;
  expectMatchesGolden(params, "sphere_with_segmentation");
}

TEST_F(GoldenImageTest, HidingSegmentationMatchesTheUnsegmentedRender) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  renderer_->setSegmentation(mivw::testing::makeSphereMask({128, 128, 128}),
                             mivw::testing::labelPalette(2));

  auto params = stillParams();
  params.segmentationVisible = false;
  expectMatchesGolden(params, "sphere_front");
}

TEST_F(GoldenImageTest, InteractiveQualityStaysPerceptuallyCloseToStill) {
  renderer_->setVolume(mivw::testing::makeShepLoganPhantom({256, 256, 128}));

  const auto still =
      mivw::testing::decodeFrame(renderer_->render(stillParams(), 1));

  auto interactive = stillParams();
  interactive.quality = render::Quality::Interactive;
  const auto fast =
      mivw::testing::decodeFrame(renderer_->render(interactive, 2));

  // The ladder trades fidelity for latency, but the user must not see a
  // materially different image while dragging.
  EXPECT_GE(mivw::testing::ssim(fast, still), 0.95);
}

TEST_F(GoldenImageTest, RenderIsDeterministicAcrossRepeatedSubmits) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  const auto params = stillParams();

  const auto first = mivw::testing::decodeFrame(renderer_->render(params, 1));
  const auto second = mivw::testing::decodeFrame(renderer_->render(params, 2));

  EXPECT_GE(mivw::testing::ssim(first, second), 0.9999);
}

TEST_F(GoldenImageTest, EmptySpaceSkippingDoesNotChangeTheImage) {
  auto params = stillParams();
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));

  renderer_->setEmptySpaceSkipping(false);
  const auto reference =
      mivw::testing::decodeFrame(renderer_->render(params, 1));

  renderer_->setEmptySpaceSkipping(true);
  const auto optimised =
      mivw::testing::decodeFrame(renderer_->render(params, 2));

  // An optimisation that alters output is a bug, not an optimisation.
  EXPECT_GE(mivw::testing::ssim(optimised, reference), 0.999);
}

TEST_F(GoldenImageTest, RecoversAfterSimulatedDeviceLoss) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  renderer_->simulateDeviceLost();

  ASSERT_NO_THROW(renderer_->recoverFromDeviceLost());
  renderer_->setVolume(mivw::testing::makeSpherePhantom({128, 128, 128}));
  expectMatchesGolden(stillParams(), "sphere_front");
}

TEST_F(GoldenImageTest, ReleasesGpuMemoryWhenTheVolumeIsReplaced) {
  renderer_->setVolume(mivw::testing::makeSpherePhantom({256, 256, 256}));
  const auto large = renderer_->gpuMemoryBytes();

  renderer_->setVolume(mivw::testing::makeSpherePhantom({64, 64, 64}));
  EXPECT_LT(renderer_->gpuMemoryBytes(), large);
}

} // namespace
