#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "mivw/cuda/stream.hpp"

namespace mivw::cuda {

class CudaError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

[[nodiscard]] bool isDeviceAvailable() noexcept;
[[nodiscard]] std::size_t freeDeviceMemoryBytes();

/// Name and driver version of the active CUDA device, for run provenance.
/// Empty strings if no device is available.
[[nodiscard]] std::string deviceName();
[[nodiscard]] std::string driverVersion();

void *allocateDevice(std::size_t bytes);
void freeDevice(void *pointer) noexcept;
void copyHostToDevice(void *dst, const void *src, std::size_t bytes,
                      const Stream &stream);
void copyDeviceToHost(void *dst, const void *src, std::size_t bytes,
                      const Stream &stream);

/// Owning device allocation.
///
/// Move-only with a deleter, so there is no manual cudaFree anywhere in the
/// codebase and an early return cannot leak device memory.
template <typename T> class DeviceBuffer {
public:
  explicit DeviceBuffer(std::size_t count)
      : count_{count},
        data_{count ? static_cast<T *>(allocateDevice(count * sizeof(T)))
                    : nullptr} {}

  DeviceBuffer(const DeviceBuffer &) = delete;
  DeviceBuffer &operator=(const DeviceBuffer &) = delete;

  DeviceBuffer(DeviceBuffer &&other) noexcept
      : count_{std::exchange(other.count_, 0)},
        data_{std::exchange(other.data_, nullptr)} {}

  DeviceBuffer &operator=(DeviceBuffer &&other) noexcept {
    if (this != &other) {
      freeDevice(data_);
      count_ = std::exchange(other.count_, 0);
      data_ = std::exchange(other.data_, nullptr);
    }
    return *this;
  }

  ~DeviceBuffer() { freeDevice(data_); }

  [[nodiscard]] T *data() noexcept { return data_; }
  [[nodiscard]] const T *data() const noexcept { return data_; }
  [[nodiscard]] std::size_t size() const noexcept { return count_; }
  [[nodiscard]] std::size_t sizeBytes() const noexcept {
    return count_ * sizeof(T);
  }
  [[nodiscard]] bool empty() const noexcept { return count_ == 0; }

  void copyFromHost(const std::vector<T> &host, const Stream &stream) {
    if (host.size() != count_) {
      throw std::invalid_argument(
          "host buffer size does not match device buffer");
    }
    copyHostToDevice(data_, host.data(), sizeBytes(), stream);
  }

  [[nodiscard]] std::vector<T> copyToHost(const Stream &stream) const {
    std::vector<T> host(count_);
    copyDeviceToHost(host.data(), data_, sizeBytes(), stream);
    return host;
  }

private:
  std::size_t count_{0};
  T *data_{nullptr};
};

} // namespace mivw::cuda
