#include "mivw/cuda/device_buffer.hpp"

namespace mivw::cuda {

struct Stream::Impl {};

Stream::Stream() : impl_{std::make_unique<Impl>()} {}
Stream::~Stream() = default;
Stream::Stream(Stream &&) noexcept = default;
Stream &Stream::operator=(Stream &&) noexcept = default;

void Stream::synchronise() const {}
void *Stream::handle() const noexcept { return nullptr; }

bool isDeviceAvailable() noexcept { return false; }
std::size_t freeDeviceMemoryBytes() { return 0; }
std::string deviceName() { return {}; }
std::string driverVersion() { return {}; }

void *allocateDevice(std::size_t) {
  throw CudaError("CUDA support is disabled");
}
void freeDevice(void *) noexcept {}

void copyHostToDevice(void *, const void *, std::size_t, const Stream &) {
  throw CudaError("CUDA support is disabled");
}

void copyDeviceToHost(void *, const void *, std::size_t, const Stream &) {
  throw CudaError("CUDA support is disabled");
}

} // namespace mivw::cuda
