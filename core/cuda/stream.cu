#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/stream.hpp"

#include <cuda_runtime.h>

#include <string>

namespace mivw::cuda {

struct Stream::Impl {
  cudaStream_t stream{};
};

Stream::Stream() : impl_{std::make_unique<Impl>()} {
  const cudaError_t err = cudaStreamCreate(&impl_->stream);
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaStreamCreate failed: ") +
                    cudaGetErrorString(err));
  }
}

Stream::~Stream() {
  if (impl_ && impl_->stream) {
    cudaStreamDestroy(impl_->stream);
  }
}

Stream::Stream(Stream &&) noexcept = default;
Stream &Stream::operator=(Stream &&) noexcept = default;

void Stream::synchronise() const {
  const cudaError_t err = cudaStreamSynchronize(impl_->stream);
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaStreamSynchronize failed: ") +
                    cudaGetErrorString(err));
  }
}

void *Stream::handle() const noexcept {
  return impl_ ? static_cast<void *>(impl_->stream) : nullptr;
}

} // namespace mivw::cuda
