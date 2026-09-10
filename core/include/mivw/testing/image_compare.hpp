#pragma once

#include <cstdint>
#include <filesystem>
#include <vector>

#include "mivw/render/renderer.hpp"

namespace mivw::testing {

struct Image {
  std::uint32_t width{0};
  std::uint32_t height{0};
  std::vector<std::uint8_t> rgba;
};

[[nodiscard]] Image decodeFrame(const render::Frame &frame);
[[nodiscard]] Image readPng(const std::filesystem::path &path);
void writePng(const std::filesystem::path &path, const Image &image);

/// Structural similarity over the luminance channel.
///
/// Golden-image tests compare perceptually rather than bit-exactly: driver
/// revisions legitimately change the last bit of a float, and an exact test
/// would fail on every GPU upgrade while catching nothing real.
[[nodiscard]] double ssim(const Image &a, const Image &b);

/// Fraction of pixels differing by more than `tolerance` in any channel.
[[nodiscard]] double pixelDifferenceRatio(const Image &a, const Image &b,
                                          std::uint8_t tolerance = 2);

} // namespace mivw::testing
