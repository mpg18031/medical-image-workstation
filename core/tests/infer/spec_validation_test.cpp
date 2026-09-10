// Input-spec validation is the safety-critical part of the inference path:
// running a model on a volume it was not trained for produces a plausible,
// confidently wrong result. These tests assert that we fail loudly instead.

#include <gtest/gtest.h>

#include <array>

#include "mivw/infer/runtime.hpp"
#include "mivw/testing/phantoms.hpp"

namespace {

using namespace mivw;

infer::ModelDescriptor makeDescriptor() {
  infer::ModelDescriptor d;
  d.name = "test-seg";
  d.version = "1.0.0";
  d.outputKind = infer::OutputKind::Segmentation;
  d.inputSpec.shape = {1, 1, 128, 128, 128};
  d.inputSpec.spacingMm = {1.0, 1.0, 1.0};
  d.inputSpec.orientation = "RAS";
  d.inputSpec.normalisation = infer::Normalisation::ZScore;
  d.inputSpec.clipHu = {-200.0F, 300.0F};
  d.inputSpec.spacingToleranceMm = 0.01;
  return d;
}

class SpecValidationTest : public ::testing::Test {
protected:
  infer::InferenceRuntime runtime;
  infer::ModelDescriptor descriptor = makeDescriptor();
};

TEST_F(SpecValidationTest, AcceptsAConformingVolume) {
  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.0, 1.0, 1.0});
  EXPECT_NO_THROW(runtime.validateInput(descriptor, volume));
}

TEST_F(SpecValidationTest, RejectsAnisotropicSpacing) {
  // The archetypal failure: clinical CT is 0.7x0.7x3.0, the model wants 1mm
  // isotropic. Resampling silently here would be indefensible.
  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {0.7, 0.7, 3.0});
  EXPECT_THROW(runtime.validateInput(descriptor, volume),
               infer::SpecMismatchError);
}

TEST_F(SpecValidationTest, ErrorMessageNamesBothExpectedAndActualSpacing) {
  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {0.7, 0.7, 3.0});
  try {
    runtime.validateInput(descriptor, volume);
    FAIL() << "expected SpecMismatchError";
  } catch (const infer::SpecMismatchError &e) {
    const std::string message = e.what();
    EXPECT_NE(message.find("spacing"), std::string::npos);
    EXPECT_NE(message.find("1"), std::string::npos);
    EXPECT_NE(message.find("3"), std::string::npos);
    // Diagnostics must never carry identifiers.
    EXPECT_EQ(message.find("Patient"), std::string::npos);
  }
}

TEST_F(SpecValidationTest, AcceptsSpacingWithinTolerance) {
  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.005, 0.998, 1.002});
  EXPECT_NO_THROW(runtime.validateInput(descriptor, volume));
}

TEST_F(SpecValidationTest, RejectsSpacingJustOutsideTolerance) {
  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.05, 1.0, 1.0});
  EXPECT_THROW(runtime.validateInput(descriptor, volume),
               infer::SpecMismatchError);
}

TEST_F(SpecValidationTest, RejectsMismatchedOrientation) {
  auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.0, 1.0, 1.0});
  volume.setDirection({-1, 0, 0, 0, -1, 0, 0, 0, 1}); // LPS, not RAS
  EXPECT_THROW(runtime.validateInput(descriptor, volume),
               infer::SpecMismatchError);
}

TEST_F(SpecValidationTest, AllowsVolumesLargerThanThePatchSize) {
  // Sliding-window inference handles this case, so it must not be rejected.
  const auto volume =
      mivw::testing::makeSpherePhantom({512, 512, 400}, {1.0, 1.0, 1.0});
  EXPECT_NO_THROW(runtime.validateInput(descriptor, volume));
}

TEST_F(SpecValidationTest, RejectsVolumesSmallerThanThePatchSize) {
  const auto volume =
      mivw::testing::makeSpherePhantom({64, 64, 64}, {1.0, 1.0, 1.0});
  EXPECT_THROW(runtime.validateInput(descriptor, volume),
               infer::SpecMismatchError);
}

TEST_F(SpecValidationTest, RefusesToLoadAnArtifactWithTheWrongDigest) {
  descriptor.artifactPath = mivw::testing::fixturePath("models/tiny_seg.onnx");
  descriptor.sha256.fill(0xAB); // deliberately wrong

  EXPECT_THROW(runtime.loadModel(descriptor), infer::DigestMismatchError);
}

TEST_F(SpecValidationTest, LoadsAnArtifactWhoseDigestMatches) {
  descriptor.artifactPath = mivw::testing::fixturePath("models/tiny_seg.onnx");
  descriptor.sha256 = mivw::testing::sha256OfFile(descriptor.artifactPath);

  EXPECT_NO_THROW(runtime.loadModel(descriptor));
}

TEST_F(SpecValidationTest, RecordsProvenanceForEveryRun) {
  if (!infer::InferenceRuntime::isDeviceAvailable()) {
    GTEST_SKIP() << "no CUDA device on this runner";
  }

  descriptor.artifactPath = mivw::testing::fixturePath("models/tiny_seg.onnx");
  descriptor.sha256 = mivw::testing::sha256OfFile(descriptor.artifactPath);
  runtime.loadModel(descriptor);

  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.0, 1.0, 1.0});
  infer::RunProvenance provenance;
  const auto result = runtime.run(descriptor, volume, provenance);

  EXPECT_EQ(result.dims(), volume.dims());
  EXPECT_EQ(provenance.modelSha256, descriptor.sha256);
  using Sha256 = std::array<std::uint8_t, 32>;
  EXPECT_NE(provenance.inputSha256, Sha256{});
  EXPECT_FALSE(provenance.runtimeVersion.empty());
  EXPECT_FALSE(provenance.gpuName.empty());
  EXPECT_GT(provenance.durationUs, 0U);
}

TEST_F(SpecValidationTest, ProducesIdenticalOutputForIdenticalInput) {
  if (!infer::InferenceRuntime::isDeviceAvailable()) {
    GTEST_SKIP() << "no CUDA device on this runner";
  }

  descriptor.artifactPath = mivw::testing::fixturePath("models/tiny_seg.onnx");
  descriptor.sha256 = mivw::testing::sha256OfFile(descriptor.artifactPath);
  runtime.loadModel(descriptor);

  const auto volume =
      mivw::testing::makeSpherePhantom({128, 128, 128}, {1.0, 1.0, 1.0});
  infer::RunProvenance p1;
  infer::RunProvenance p2;

  const auto a = runtime.run(descriptor, volume, p1);
  const auto b = runtime.run(descriptor, volume, p2);

  // Reproducibility is a precondition for auditability.
  EXPECT_EQ(mivw::testing::sha256OfVolume(a), mivw::testing::sha256OfVolume(b));
}

TEST_F(SpecValidationTest, EngineCacheKeyIncludesDriverAndRuntimeVersions) {
  const auto key = infer::InferenceRuntime::engineCacheKey(descriptor.sha256,
                                                           "sm_86", "10.4.0");
  const auto other = infer::InferenceRuntime::engineCacheKey(descriptor.sha256,
                                                             "sm_86", "10.5.0");

  // A stale engine silently reused across a TensorRT upgrade is a
  // correctness hazard, so the version must be part of the key.
  EXPECT_NE(key, other);
}

} // namespace
