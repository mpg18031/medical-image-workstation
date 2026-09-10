#include "mivw/dicom/dataset.hpp"
#include "mivw/dicom/deidentifier.hpp"

#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dctk.h>

#include <unordered_set>

namespace mivw::dicom {

namespace {
DcmTagKey toKey(Tag tag) { return {tag.group, tag.element}; }
} // namespace

struct DicomDataset::Impl {
  DcmFileFormat fileformat;
};

DicomDataset::DicomDataset() : impl_{std::make_unique<Impl>()} {}
DicomDataset::DicomDataset(DicomDataset &&) noexcept = default;
DicomDataset &DicomDataset::operator=(DicomDataset &&) noexcept = default;
DicomDataset::~DicomDataset() = default;

DicomDataset DicomDataset::load(const std::filesystem::path &path) {
  DicomDataset dataset;
  const OFCondition status =
      dataset.impl_->fileformat.loadFile(path.string().c_str());
  if (status.bad()) {
    throw DicomDataError("failed to load DICOM file " + path.string() + ": " +
                         status.text());
  }
  return dataset;
}

bool DicomDataset::hasTag(Tag tag) const {
  return impl_->fileformat.getDataset()->tagExists(toKey(tag));
}

std::string DicomDataset::getString(Tag tag) const {
  OFString value;
  const OFCondition status =
      impl_->fileformat.getDataset()->findAndGetOFStringArray(toKey(tag),
                                                              value);
  if (status.bad()) {
    throw DicomDataError("tag not present or not readable");
  }
  return value.c_str();
}

std::vector<Tag> DicomDataset::allTags() const {
  std::vector<Tag> tags;
  DcmDataset *dataset = impl_->fileformat.getDataset();
  const unsigned long count = dataset->card();
  tags.reserve(count);
  for (unsigned long i = 0; i < count; ++i) {
    if (DcmElement *elem = dataset->getElement(i)) {
      tags.push_back({elem->getGTag(), elem->getETag()});
    }
  }
  return tags;
}

void DicomDataset::setString(Tag tag, const std::string &value) {
  const DcmTag dcmTag(tag.group, tag.element);
  const OFCondition status =
      impl_->fileformat.getDataset()->putAndInsertString(dcmTag, value.c_str());
  if (status.bad()) {
    throw DicomDataError(std::string("failed to set tag value: ") +
                         status.text());
  }
}

void DicomDataset::removeTag(Tag tag) {
  impl_->fileformat.getDataset()->findAndDeleteElement(toKey(tag));
}

void DicomDataset::removeAllPrivateTags() {
  DcmDataset *dataset = impl_->fileformat.getDataset();
  for (long i = static_cast<long>(dataset->card()) - 1; i >= 0; --i) {
    auto index = static_cast<unsigned long>(i);
    DcmElement *elem = dataset->getElement(index);
    if (elem && elem->getGTag() % 2 != 0) {
      delete dataset->remove(index);
    }
  }
}

std::string DicomDataset::sopClassUid() const {
  return hasTag({0x0008, 0x0016}) ? getString({0x0008, 0x0016}) : std::string{};
}

std::string DicomDataset::modality() const {
  return hasTag({0x0008, 0x0060}) ? getString({0x0008, 0x0060}) : std::string{};
}

void DicomDataset::save(const std::filesystem::path &path) const {
  const OFCondition status = impl_->fileformat.saveFile(path.string().c_str());
  if (status.bad()) {
    throw DicomDataError(std::string("failed to save DICOM file: ") +
                         status.text());
  }
}

bool isSupportedSopClass(const std::string &sopClassUid) {
  static const std::unordered_set<std::string> kSupported{
      UID_CTImageStorage,
      UID_MRImageStorage,
      UID_PositronEmissionTomographyImageStorage,
      UID_UltrasoundImageStorage,
      UID_XRayAngiographicImageStorage,
      UID_ComputedRadiographyImageStorage,
      UID_SecondaryCaptureImageStorage,
      UID_DigitalXRayImageStorageForPresentation,
      UID_DigitalMammographyXRayImageStorageForPresentation,
  };
  return kSupported.contains(sopClassUid);
}

} // namespace mivw::dicom
