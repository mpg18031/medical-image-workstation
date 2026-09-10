#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>

#include "mivw/volume/volume.hpp"

namespace mivw::render {

/// The GPU dropped the device. Recoverable, but every resource must be
/// recreated and every volume re-uploaded.
class DeviceLostError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

struct Camera {
  std::array<float, 3> eye{0.0F, 0.0F, -500.0F};
  std::array<float, 3> target{0.0F, 0.0F, 0.0F};
  std::array<float, 3> up{0.0F, 1.0F, 0.0F};
  float fovDegrees{45.0F};
};

struct WindowLevel {
  float center{40.0F};
  float width{400.0F};
};

enum class Quality : std::uint8_t {
  Interactive, ///< Half resolution, coarse step. Used while input is active.
  Still        ///< Full resolution. Emitted once input goes quiet.
};

struct RenderParams {
  Camera camera;
  WindowLevel window;
  Quality quality{Quality::Interactive};
  std::uint32_t width{1024};
  std::uint32_t height{1024};
  float segmentationOpacity{0.45F};
  bool segmentationVisible{true};
  std::string transferFunctionPreset{"ct-soft-tissue"};
};

struct Frame {
  std::uint32_t sequence{0};
  std::uint32_t width{0};
  std::uint32_t height{0};
  std::uint32_t renderTimeUs{0};
  std::string codec{"h264"};
  std::span<const std::byte> payload; ///< Valid until the next submit.
};

/// Off-screen Vulkan volume renderer.
///
/// Renders to a colour attachment rather than a swapchain, so the same code
/// path serves both local and server deployment modes (see ADR 0001).
class Renderer {
public:
  /// True when a Vulkan device is present. Tests skip rather than fail on
  /// runners without one.
  [[nodiscard]] static bool isDeviceAvailable() noexcept;

  Renderer();
  ~Renderer();

  Renderer(const Renderer &) = delete;
  Renderer &operator=(const Renderer &) = delete;
  Renderer(Renderer &&) noexcept;
  Renderer &operator=(Renderer &&) noexcept;

  /// Uploads the volume as a 3D texture and builds the min/max occupancy grid
  /// used for empty-space skipping. Pins GPU memory until released.
  void setVolume(const volume::Volume &volume);

  /// Optional label mask composited over the volume.
  void setSegmentation(const volume::Volume &mask,
                       std::span<const std::array<float, 4>> labelColours);

  /// Blocking render. Returns a view into an internal staging buffer.
  [[nodiscard]] Frame render(const RenderParams &params,
                             std::uint32_t sequence);

  /// Recreates the device after VK_ERROR_DEVICE_LOST. Volumes must be
  /// re-uploaded.
  void recoverFromDeviceLost();

  /// Empty-space skipping must not change the image, only the time taken.
  /// Toggleable so a test can assert exactly that.
  void setEmptySpaceSkipping(bool enabled) noexcept;

  /// Forces the next submit to report device loss, for recovery tests.
  void simulateDeviceLost();

  [[nodiscard]] std::size_t gpuMemoryBytes() const noexcept;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace mivw::render
