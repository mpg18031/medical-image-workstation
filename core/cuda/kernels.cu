#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/kernels.hpp"

#include <cuda_runtime.h>

#include <cstdint>
#include <stdexcept>
#include <string>

namespace mivw::cuda {

namespace {

constexpr int kBlockSize1D = 256;

__device__ __forceinline__ std::size_t linearIndex(int x, int y, int z, int nx,
                                                   int ny) {
  return (static_cast<std::size_t>(z) * static_cast<std::size_t>(ny) +
          static_cast<std::size_t>(y)) *
             static_cast<std::size_t>(nx) +
         static_cast<std::size_t>(x);
}

__device__ __forceinline__ int clampInt(int v, int lo, int hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

__global__ void windowLevelKernel(const std::int16_t *in, float *out,
                                  std::size_t n, float lo, float width) {
  const std::size_t i =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i >= n)
    return;
  const float v = (static_cast<float>(in[i]) - lo) / width;
  out[i] = fminf(fmaxf(v, 0.0F), 1.0F);
}

__global__ void gradientKernel(const float *in, float3 *out, int nx, int ny,
                               int nz, float sx, float sy, float sz) {
  const int x = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int y = static_cast<int>(blockIdx.y * blockDim.y + threadIdx.y);
  const int z = static_cast<int>(blockIdx.z * blockDim.z + threadIdx.z);
  if (x >= nx || y >= ny || z >= nz)
    return;

  auto at = [&](int xx, int yy, int zz) {
    return in[linearIndex(clampInt(xx, 0, nx - 1), clampInt(yy, 0, ny - 1),
                          clampInt(zz, 0, nz - 1), nx, ny)];
  };

  float3 g;
  g.x = (at(x + 1, y, z) - at(x - 1, y, z)) / (2.0F * sx);
  g.y = (at(x, y + 1, z) - at(x, y - 1, z)) / (2.0F * sy);
  g.z = (at(x, y, z + 1) - at(x, y, z - 1)) / (2.0F * sz);
  out[linearIndex(x, y, z, nx, ny)] = g;
}

__global__ void occupancyGridKernel(const std::int16_t *in, std::uint8_t *out,
                                    int nx, int ny, int nz, int cellsPerAxis,
                                    std::int16_t emptyThreshold) {
  const int cx = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  const int cy = static_cast<int>(blockIdx.y * blockDim.y + threadIdx.y);
  const int cz = static_cast<int>(blockIdx.z * blockDim.z + threadIdx.z);
  if (cx >= cellsPerAxis || cy >= cellsPerAxis || cz >= cellsPerAxis)
    return;

  const int x0 = cx * nx / cellsPerAxis;
  const int x1 = (cx + 1) * nx / cellsPerAxis;
  const int y0 = cy * ny / cellsPerAxis;
  const int y1 = (cy + 1) * ny / cellsPerAxis;
  const int z0 = cz * nz / cellsPerAxis;
  const int z1 = (cz + 1) * nz / cellsPerAxis;

  std::uint8_t occupied = 0;
  for (int z = z0; z < z1 && !occupied; ++z) {
    for (int y = y0; y < y1 && !occupied; ++y) {
      for (int x = x0; x < x1; ++x) {
        if (in[linearIndex(x, y, z, nx, ny)] > emptyThreshold) {
          occupied = 1;
          break;
        }
      }
    }
  }
  const std::size_t cellIndex =
      (static_cast<std::size_t>(cz) * static_cast<std::size_t>(cellsPerAxis) +
       static_cast<std::size_t>(cy)) *
          static_cast<std::size_t>(cellsPerAxis) +
      static_cast<std::size_t>(cx);
  out[cellIndex] = occupied;
}

__global__ void histogramKernel(const std::int16_t *in, std::uint32_t *bins,
                                std::size_t n, std::int16_t minValue,
                                std::int16_t maxValue, std::uint32_t binCount) {
  const std::size_t i =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i >= n)
    return;
  const std::int16_t v = in[i];
  if (v < minValue || v > maxValue)
    return;
  const float range = static_cast<float>(maxValue - minValue) + 1.0F;
  auto bin =
      static_cast<std::uint32_t>((static_cast<float>(v - minValue) / range) *
                                 static_cast<float>(binCount));
  if (bin >= binCount)
    bin = binCount - 1;
  atomicAdd(&bins[bin], 1U);
}

void checkLaunch(const char *what) {
  const cudaError_t err = cudaGetLastError();
  if (err != cudaSuccess) {
    throw CudaError(std::string(what) + " failed: " + cudaGetErrorString(err));
  }
}

} // namespace

void launchWindowLevel(const DeviceBuffer<std::int16_t> &input,
                       DeviceBuffer<float> &output, float center, float width,
                       const Stream &stream) {
  if (width <= 0.0F) {
    throw std::invalid_argument("window width must be positive");
  }
  if (input.size() != output.size()) {
    throw std::invalid_argument("window input/output size mismatch");
  }
  const std::size_t n = input.size();
  if (n == 0)
    return;
  const float lo = center - 0.5F * width;
  const auto blocks =
      static_cast<unsigned>((n + kBlockSize1D - 1) / kBlockSize1D);
  windowLevelKernel<<<blocks, kBlockSize1D, 0,
                      static_cast<cudaStream_t>(stream.handle())>>>(
      input.data(), output.data(), n, lo, width);
  checkLaunch("launchWindowLevel");
}

void launchGradient(const DeviceBuffer<float> &input,
                    DeviceBuffer<float3> &output, Dims3 dims,
                    Spacing3 spacingMm, const Stream &stream) {
  const auto expected = static_cast<std::size_t>(dims[0]) *
                        static_cast<std::size_t>(dims[1]) *
                        static_cast<std::size_t>(dims[2]);
  if (input.size() != expected || output.size() != expected) {
    throw std::invalid_argument("gradient dims do not match buffer size");
  }
  const dim3 block(8, 8, 8);
  const dim3 grid(static_cast<unsigned>((dims[0] + 7) / 8),
                  static_cast<unsigned>((dims[1] + 7) / 8),
                  static_cast<unsigned>((dims[2] + 7) / 8));
  gradientKernel<<<grid, block, 0,
                   static_cast<cudaStream_t>(stream.handle())>>>(
      input.data(), output.data(), dims[0], dims[1], dims[2], spacingMm[0],
      spacingMm[1], spacingMm[2]);
  checkLaunch("launchGradient");
}

void launchOccupancyGrid(const DeviceBuffer<std::int16_t> &input,
                         DeviceBuffer<std::uint8_t> &output, Dims3 dims,
                         int cellsPerAxis, std::int16_t emptyThreshold,
                         const Stream &stream) {
  const auto expectedIn = static_cast<std::size_t>(dims[0]) *
                          static_cast<std::size_t>(dims[1]) *
                          static_cast<std::size_t>(dims[2]);
  const auto expectedOut = static_cast<std::size_t>(cellsPerAxis) *
                           static_cast<std::size_t>(cellsPerAxis) *
                           static_cast<std::size_t>(cellsPerAxis);
  if (input.size() != expectedIn || output.size() != expectedOut) {
    throw std::invalid_argument("occupancy grid dims do not match buffer size");
  }
  const dim3 block(8, 8, 8);
  const dim3 grid(static_cast<unsigned>((cellsPerAxis + 7) / 8),
                  static_cast<unsigned>((cellsPerAxis + 7) / 8),
                  static_cast<unsigned>((cellsPerAxis + 7) / 8));
  occupancyGridKernel<<<grid, block, 0,
                        static_cast<cudaStream_t>(stream.handle())>>>(
      input.data(), output.data(), dims[0], dims[1], dims[2], cellsPerAxis,
      emptyThreshold);
  checkLaunch("launchOccupancyGrid");
}

void launchHistogram(const DeviceBuffer<std::int16_t> &input,
                     DeviceBuffer<std::uint32_t> &bins, std::int16_t minValue,
                     std::int16_t maxValue, const Stream &stream) {
  if (maxValue < minValue) {
    throw std::invalid_argument("histogram maxValue must be >= minValue");
  }
  const std::size_t n = input.size();
  if (n == 0)
    return;
  cudaMemsetAsync(bins.data(), 0, bins.sizeBytes(),
                  static_cast<cudaStream_t>(stream.handle()));
  const auto blocks =
      static_cast<unsigned>((n + kBlockSize1D - 1) / kBlockSize1D);
  histogramKernel<<<blocks, kBlockSize1D, 0,
                    static_cast<cudaStream_t>(stream.handle())>>>(
      input.data(), bins.data(), n, minValue, maxValue,
      static_cast<std::uint32_t>(bins.size()));
  checkLaunch("launchHistogram");
}

} // namespace mivw::cuda
