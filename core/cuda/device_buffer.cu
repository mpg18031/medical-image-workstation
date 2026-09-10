#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/stream.hpp"

#include <cuda_runtime.h>

#include <string>

namespace mivw::cuda {

bool isDeviceAvailable() noexcept {
  int count = 0;
  const cudaError_t err = cudaGetDeviceCount(&count);
  return err == cudaSuccess && count > 0;
}

std::size_t freeDeviceMemoryBytes() {
  std::size_t freeBytes = 0;
  std::size_t totalBytes = 0;
  const cudaError_t err = cudaMemGetInfo(&freeBytes, &totalBytes);
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaMemGetInfo failed: ") +
                    cudaGetErrorString(err));
  }
  return freeBytes;
}

std::string deviceName() {
  if (!isDeviceAvailable())
    return {};
  int device = 0;
  if (cudaGetDevice(&device) != cudaSuccess)
    return {};
  cudaDeviceProp props{};
  if (cudaGetDeviceProperties(&props, device) != cudaSuccess)
    return {};
  return props.name;
}

std::string driverVersion() {
  if (!isDeviceAvailable())
    return {};
  int version = 0;
  if (cudaDriverGetVersion(&version) != cudaSuccess)
    return {};
  return std::to_string(version / 1000) + "." +
         std::to_string((version % 1000) / 10);
}

void *allocateDevice(std::size_t bytes) {
  if (bytes == 0) {
    return nullptr;
  }
  void *pointer = nullptr;
  const cudaError_t err = cudaMalloc(&pointer, bytes);
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaMalloc failed: ") +
                    cudaGetErrorString(err));
  }
  return pointer;
}

void freeDevice(void *pointer) noexcept {
  if (pointer) {
    cudaFree(pointer);
  }
}

void copyHostToDevice(void *dst, const void *src, std::size_t bytes,
                      const Stream &stream) {
  const cudaError_t err =
      cudaMemcpyAsync(dst, src, bytes, cudaMemcpyHostToDevice,
                      static_cast<cudaStream_t>(stream.handle()));
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaMemcpyAsync (H2D) failed: ") +
                    cudaGetErrorString(err));
  }
}

void copyDeviceToHost(void *dst, const void *src, std::size_t bytes,
                      const Stream &stream) {
  const cudaError_t err =
      cudaMemcpyAsync(dst, src, bytes, cudaMemcpyDeviceToHost,
                      static_cast<cudaStream_t>(stream.handle()));
  if (err != cudaSuccess) {
    throw CudaError(std::string("cudaMemcpyAsync (D2H) failed: ") +
                    cudaGetErrorString(err));
  }
}

} // namespace mivw::cuda
