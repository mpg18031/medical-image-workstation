#pragma once

#include <memory>

namespace mivw::cuda {

/// Owning CUDA stream.
///
/// Non-default stream by default, so kernel launches do not serialise against
/// unrelated work on the legacy default stream.
class Stream {
public:
  Stream();
  ~Stream();

  Stream(const Stream &) = delete;
  Stream &operator=(const Stream &) = delete;
  Stream(Stream &&) noexcept;
  Stream &operator=(Stream &&) noexcept;

  void synchronise() const;

  /// Opaque `cudaStream_t`. Kept as void* so this header stays usable from
  /// translation units compiled without nvcc.
  [[nodiscard]] void *handle() const noexcept;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace mivw::cuda
