#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace mivw::dicom {

struct Tag;

class DicomDataError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

class DeIdentificationError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

/// Thin owning wrapper over a DCMTK dataset.
///
/// Exists so the rest of the core never includes DCMTK headers directly, which
/// keeps its macro-heavy API from leaking across the codebase.
class DicomDataset {
public:
  [[nodiscard]] static DicomDataset load(const std::filesystem::path &path);

  DicomDataset(const DicomDataset &) = delete;
  DicomDataset &operator=(const DicomDataset &) = delete;
  DicomDataset(DicomDataset &&) noexcept;
  DicomDataset &operator=(DicomDataset &&) noexcept;
  ~DicomDataset();

  [[nodiscard]] bool hasTag(Tag tag) const;
  [[nodiscard]] std::string getString(Tag tag) const;
  [[nodiscard]] std::vector<Tag> allTags() const;

  void setString(Tag tag, const std::string &value);
  void removeTag(Tag tag);

  /// Removes every odd-group (private) element. Vendors habitually store
  /// identifiers there, so an allow-list would be unsafe.
  void removeAllPrivateTags();

  [[nodiscard]] std::string sopClassUid() const;
  [[nodiscard]] std::string modality() const;

  void save(const std::filesystem::path &path) const;

private:
  DicomDataset();

  struct Impl;
  std::unique_ptr<Impl> impl_;
};

/// SOP classes this workstation is prepared to reconstruct. Anything else is
/// rejected rather than partially handled.
[[nodiscard]] bool isSupportedSopClass(const std::string &sopClassUid);

} // namespace mivw::dicom
