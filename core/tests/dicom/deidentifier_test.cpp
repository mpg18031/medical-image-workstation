#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "mivw/dicom/dataset.hpp"
#include "mivw/dicom/deidentifier.hpp"

namespace {

using namespace mivw::dicom;

std::filesystem::path fixture(const std::string &name) {
  return std::filesystem::path{MIVW_FIXTURE_DIR} / "generated" / name;
}

class DeIdentifierTest : public ::testing::Test {
protected:
  DeIdentifier deid{DeIdPolicy::basicProfile()};
};

TEST_F(DeIdentifierTest, RemovesEveryBasicProfileTag) {
  auto ds = DicomDataset::load(fixture("synthetic_ct_with_phi.dcm"));
  deid.apply(ds);

  const auto policy = DeIdPolicy::basicProfile();
  for (const auto &tag : policy.removedTags()) {
    EXPECT_FALSE(ds.hasTag(tag))
        << "leaked tag (" << std::hex << tag.group << "," << tag.element << ")";
  }
}

TEST_F(DeIdentifierTest, StripsAllPrivateTags) {
  // Vendors routinely stash identifiers in private blocks, so the profile
  // removes the whole odd-group space rather than an allow-list.
  auto ds = DicomDataset::load(fixture("synthetic_ct_private_tags.dcm"));
  deid.apply(ds);

  for (const auto &tag : ds.allTags()) {
    EXPECT_EQ(tag.group % 2, 0u) << "private tag survived de-identification";
  }
}

TEST_F(DeIdentifierTest, PseudonymisesUidsConsistently) {
  auto first = DicomDataset::load(fixture("synthetic_ct_slice_001.dcm"));
  auto second = DicomDataset::load(fixture("synthetic_ct_slice_002.dcm"));

  const auto a = deid.apply(first);
  const auto b = deid.apply(second);

  // Slices of one series must still resolve to the same series after
  // pseudonymisation, otherwise the study can never be reassembled.
  EXPECT_EQ(a.pseudonymisedStudyUid, b.pseudonymisedStudyUid);
  EXPECT_EQ(a.pseudonymisedSeriesUid, b.pseudonymisedSeriesUid);
  EXPECT_EQ(a.pseudonymisedPatientId, b.pseudonymisedPatientId);
}

TEST_F(DeIdentifierTest, PseudonymisedUidsDoNotEmbedTheOriginal) {
  auto ds = DicomDataset::load(fixture("synthetic_ct_slice_001.dcm"));
  const std::string original = ds.getString({0x0020, 0x000D});
  const auto result = deid.apply(ds);

  EXPECT_NE(result.pseudonymisedStudyUid, original);
  EXPECT_EQ(result.pseudonymisedStudyUid.find(original), std::string::npos);
}

TEST_F(DeIdentifierTest, AppliesTheSameDateShiftAcrossOnePatient) {
  const DeIdPolicy policy = DeIdPolicy::basicProfile();
  const int first = policy.dateShiftDays("patient-key-A");
  const int second = policy.dateShiftDays("patient-key-A");
  const int other = policy.dateShiftDays("patient-key-B");

  // Temporal relationships between a patient's studies must survive; absolute
  // dates must not.
  EXPECT_EQ(first, second);
  EXPECT_NE(first, other);
  EXPECT_NE(first, 0);
}

TEST_F(DeIdentifierTest, RetainsGeometryNeededForReconstruction) {
  auto ds = DicomDataset::load(fixture("synthetic_ct_slice_001.dcm"));
  deid.apply(ds);

  EXPECT_TRUE(ds.hasTag({0x0028, 0x0030})); // PixelSpacing
  EXPECT_TRUE(ds.hasTag({0x0020, 0x0037})); // ImageOrientationPatient
  EXPECT_TRUE(ds.hasTag({0x0020, 0x0032})); // ImagePositionPatient
  EXPECT_TRUE(ds.hasTag({0x0028, 0x1052})); // RescaleIntercept
  EXPECT_TRUE(ds.hasTag({0x0008, 0x0060})); // Modality
}

TEST_F(DeIdentifierTest, CoarsensBirthDateToYear) {
  auto ds = DicomDataset::load(fixture("synthetic_ct_with_phi.dcm"));
  deid.apply(ds);

  if (ds.hasTag({0x0010, 0x0030})) {
    const std::string dob = ds.getString({0x0010, 0x0030});
    EXPECT_EQ(dob.substr(4), "0101") << "full date of birth retained";
  }
}

TEST_F(DeIdentifierTest, QuarantinesSeriesWithBurnedInAnnotation) {
  auto ds = DicomDataset::load(fixture("synthetic_us_burned_in.dcm"));
  const auto result = deid.apply(ds);

  // Header scrubbing cannot remove text rendered into the pixels, so these
  // must never pass silently.
  EXPECT_TRUE(result.quarantined);
  EXPECT_THAT(result.quarantineReason, ::testing::HasSubstr("burned-in"));
}

TEST_F(DeIdentifierTest, QuarantinesAtRiskModalityWhenFlagIsAbsent) {
  auto ds = DicomDataset::load(fixture("synthetic_xa_no_burnin_flag.dcm"));
  const auto result = deid.apply(ds);

  // Absent flag on an at-risk modality is treated as "unknown", not "no".
  EXPECT_TRUE(result.quarantined);
}

TEST_F(DeIdentifierTest, DoesNotQuarantineCtWithoutBurnedInAnnotation) {
  auto ds = DicomDataset::load(fixture("synthetic_ct_slice_001.dcm"));
  EXPECT_FALSE(deid.apply(ds).quarantined);
}

TEST(BurnInRisk, FlagsModalitiesThatCommonlyRenderTextIntoPixels) {
  for (const auto *modality : {"US", "XA", "CR", "SC", "DX", "MG"}) {
    EXPECT_TRUE(isBurnInRiskModality(modality)) << modality;
  }
  for (const auto *modality : {"CT", "MR", "PT"}) {
    EXPECT_FALSE(isBurnInRiskModality(modality)) << modality;
  }
}

TEST_F(DeIdentifierTest,
       ThrowsOnUnsupportedSopClassRatherThanPassingItThrough) {
  auto ds = DicomDataset::load(fixture("synthetic_unsupported_sop.dcm"));
  EXPECT_THROW(deid.apply(ds), DeIdentificationError);
}

} // namespace
