#include "mivw/dicom/deidentifier.hpp"

#include <array>
#include <functional>
#include <iomanip>
#include <sstream>
#include <string_view>

namespace mivw::dicom {

namespace {

constexpr Tag kPatientName{0x0010, 0x0010};
constexpr Tag kPatientId{0x0010, 0x0020};
constexpr Tag kPatientBirthDate{0x0010, 0x0030};
constexpr Tag kPatientAddress{0x0010, 0x1040};
constexpr Tag kPatientTelephoneNumbers{0x0010, 0x2154};
constexpr Tag kReferringPhysicianName{0x0008, 0x0090};
constexpr Tag kInstitutionName{0x0008, 0x0080};
constexpr Tag kOperatorsName{0x0008, 0x1070};
constexpr Tag kDeviceSerialNumber{0x0018, 0x1000};
constexpr Tag kAccessionNumber{0x0008, 0x0050};
constexpr Tag kStudyInstanceUid{0x0020, 0x000D};
constexpr Tag kSeriesInstanceUid{0x0020, 0x000E};
constexpr Tag kBurnedInAnnotation{0x0028, 0x0301};

std::uint64_t hashOf(const std::string &value) {
  return std::hash<std::string>{}(value);
}

/// UID-shaped so it survives round-tripping through UI-VR elements, but the
/// digits are a one-way hash: the original identifier cannot be recovered.
std::string pseudonymiseUid(const std::string &original) {
  std::ostringstream oss;
  oss << "2.25." << hashOf("uid|" + original);
  return oss.str();
}

std::string pseudonymisePatientId(const std::string &original) {
  std::ostringstream oss;
  oss << "ANON" << std::hex << std::setfill('0') << std::setw(16)
      << hashOf("patient|" + original);
  return oss.str();
}

} // namespace

DeIdPolicy DeIdPolicy::basicProfile() {
  DeIdPolicy policy;
  policy.removed_ = {
      kPatientName,
      kPatientAddress,
      kPatientTelephoneNumbers,
      kReferringPhysicianName,
      kInstitutionName,
      kOperatorsName,
      kDeviceSerialNumber,
      kAccessionNumber,
  };
  policy.pseudonymised_ = {kPatientId, kStudyInstanceUid, kSeriesInstanceUid};
  policy.coarsened_ = {kPatientBirthDate};
  return policy;
}

TagAction DeIdPolicy::actionFor(Tag tag) const noexcept {
  for (const auto &t : removed_) {
    if (t == tag)
      return TagAction::Remove;
  }
  for (const auto &t : pseudonymised_) {
    if (t == tag)
      return TagAction::Pseudonymise;
  }
  for (const auto &t : coarsened_) {
    if (t == tag)
      return TagAction::Coarsen;
  }
  return TagAction::Retain;
}

const std::vector<Tag> &DeIdPolicy::removedTags() const noexcept {
  return removed_;
}

int DeIdPolicy::dateShiftDays(const std::string &patientKey) const {
  const std::uint64_t hash = hashOf("dateshift|" + patientKey);
  int shift =
      static_cast<int>(hash % 729) - 364; // spread over roughly +/- 1 year
  if (shift == 0)
    shift = 1; // never "no shift"
  return shift;
}

bool isBurnInRiskModality(const std::string &modality) noexcept {
  static constexpr std::array<std::string_view, 6> kRiskyModalities{
      "US", "XA", "CR", "SC", "DX", "MG"};
  for (const auto &m : kRiskyModalities) {
    if (m == modality)
      return true;
  }
  return false;
}

DeIdentifier::DeIdentifier(DeIdPolicy policy) : policy_{std::move(policy)} {}

DeIdResult DeIdentifier::apply(DicomDataset &dataset) const {
  if (!isSupportedSopClass(dataset.sopClassUid())) {
    throw DeIdentificationError("unsupported SOP class: " +
                                dataset.sopClassUid());
  }

  DeIdResult result;

  const std::string modality = dataset.modality();
  if (isBurnInRiskModality(modality)) {
    const bool hasFlag = dataset.hasTag(kBurnedInAnnotation);
    const std::string flag =
        hasFlag ? dataset.getString(kBurnedInAnnotation) : std::string{};
    if (hasFlag && flag == "NO") {
      result.quarantined = false;
    } else if (hasFlag && flag == "YES") {
      result.quarantined = true;
      result.quarantineReason = "modality reports a burned-in annotation";
    } else {
      // Absent flag on an at-risk modality means "unknown", not "no".
      result.quarantined = true;
      result.quarantineReason =
          "at-risk modality with no burned-in annotation flag present";
    }
  }

  const std::string patientId =
      dataset.hasTag(kPatientId) ? dataset.getString(kPatientId) : "";
  const std::string studyUid = dataset.hasTag(kStudyInstanceUid)
                                   ? dataset.getString(kStudyInstanceUid)
                                   : "";
  const std::string seriesUid = dataset.hasTag(kSeriesInstanceUid)
                                    ? dataset.getString(kSeriesInstanceUid)
                                    : "";

  result.pseudonymisedPatientId = pseudonymisePatientId(patientId);
  result.pseudonymisedStudyUid = pseudonymiseUid(studyUid);
  result.pseudonymisedSeriesUid = pseudonymiseUid(seriesUid);
  result.dateShiftDays = policy_.dateShiftDays(patientId);

  for (const auto &tag : policy_.removedTags()) {
    if (dataset.hasTag(tag))
      dataset.removeTag(tag);
  }

  if (dataset.hasTag(kPatientId))
    dataset.setString(kPatientId, result.pseudonymisedPatientId);
  if (dataset.hasTag(kStudyInstanceUid)) {
    dataset.setString(kStudyInstanceUid, result.pseudonymisedStudyUid);
  }
  if (dataset.hasTag(kSeriesInstanceUid)) {
    dataset.setString(kSeriesInstanceUid, result.pseudonymisedSeriesUid);
  }

  if (dataset.hasTag(kPatientBirthDate)) {
    const std::string dob = dataset.getString(kPatientBirthDate);
    if (dob.size() >= 4) {
      dataset.setString(kPatientBirthDate, dob.substr(0, 4) + "0101");
    }
  }

  dataset.removeAllPrivateTags();

  return result;
}

} // namespace mivw::dicom
