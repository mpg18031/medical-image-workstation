#pragma once

#include <array>
#include <cstdint>

#include "mivw/cuda/device_buffer.hpp"
#include "mivw/cuda/stream.hpp"

#ifdef __CUDACC__
#include <vector_types.h>
#else
struct float3 {
  float x, y, z;
};
#endif

namespace mivw::cuda {

using Dims3 = std::array<int, 3>;
using Spacing3 = std::array<float, 3>;

/// Maps stored values into [0, 1] using the DICOM window/level convention.
/// Throws std::invalid_argument when width <= 0 rather than dividing by zero.
void launchWindowLevel(const DeviceBuffer<std::int16_t> &input,
                       DeviceBuffer<float> &output, float center, float width,
                       const Stream &stream);

/// Central-difference gradient, divided by voxel spacing so shading normals
/// stay correct on anisotropic clinical data.
void launchGradient(const DeviceBuffer<float> &input,
                    DeviceBuffer<float3> &output, Dims3 dims,
                    Spacing3 spacingMm, const Stream &stream);

/// Min/max occupancy grid used by the renderer for empty-space skipping.
void launchOccupancyGrid(const DeviceBuffer<std::int16_t> &input,
                         DeviceBuffer<std::uint8_t> &output, Dims3 dims,
                         int cellsPerAxis, std::int16_t emptyThreshold,
                         const Stream &stream);

/// Intensity histogram, used for transfer-function auto-ranging.
void launchHistogram(const DeviceBuffer<std::int16_t> &input,
                     DeviceBuffer<std::uint32_t> &bins, std::int16_t minValue,
                     std::int16_t maxValue, const Stream &stream);

} // namespace mivw::cuda
