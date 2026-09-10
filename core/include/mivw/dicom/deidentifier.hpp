#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "mivw/dicom/dataset.hpp"

namespace mivw::dicom {

struct Tag {
  std::uint16_t group;
  std::uint16_t element;

  friend bool operator==(const Tag &, const Tag &) = default;
};

enum class TagAction : std::uint8_t {
  Remove,       ///< Delete the attribute entirely.
  Pseudonymise, ///< Replace with a consistent, non-reversible surrogate.
  Coarsen,      ///< Reduce precision (dates -> year, ages -> bands).
  Retain        ///< Keep; required for correct reconstruction or rendering.
};

/// Policy implementing DICOM PS3.15 Annex E Basic Confidentiality Profile.
class DeIdPolicy {
public:
  [[nodiscard]] static DeIdPolicy basicProfile();

  [[nodiscard]] TagAction actionFor(Tag tag) const noexcept;
  [[nodiscard]] const std::vector<Tag> &removedTags() const noexcept;

  /// Consistent per-patient date shift, in days. Preserves temporal
  /// relationships between studies while destroying absolute dates.
  [[nodiscard]] int dateShiftDays(const std::string &patientKey) const;

private:
  std::vector<Tag> removed_;
  std::vector<Tag> pseudonymised_;
  std::vector<Tag> coarsened_;
};

/// Modalities where text is commonly burned into the pixel data. Header
/// scrubbing cannot remove that, so these are quarantined unless
/// BurnedInAnnotation is explicitly NO.
[[nodiscard]] bool isBurnInRiskModality(const std::string &modality) noexcept;

struct DeIdResult {
  std::string pseudonymisedPatientId;
  std::string pseudonymisedStudyUid;
  std::string pseudonymisedSeriesUid;
  int dateShiftDays{0};
  bool quarantined{false};
  std::string quarantineReason;
};

class DeIdentifier {
public:
  explicit DeIdentifier(DeIdPolicy policy);

  /// Mutates the dataset in place. Must run before anything is persisted
  /// outside the ingest sandbox. Throws DeIdentificationError on an
  /// unsupported SOP class rather than passing it through unscrubbed.
  DeIdResult apply(DicomDataset &dataset) const;

private:
  DeIdPolicy policy_;
};

} // namespace mivw::dicom
