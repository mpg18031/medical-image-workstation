#include "mivw/testing/image_compare.hpp"

#include <png.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace mivw::testing {

Image decodeFrame(const render::Frame &frame) {
  // The renderer emits raw tightly-packed RGBA8 in the frame payload; there
  // is no video codec in this build (see Renderer::render).
  Image image;
  image.width = frame.width;
  image.height = frame.height;
  image.rgba.assign(
      reinterpret_cast<const std::uint8_t *>(frame.payload.data()),
      reinterpret_cast<const std::uint8_t *>(frame.payload.data()) +
          frame.payload.size());
  return image;
}

Image readPng(const std::filesystem::path &path) {
  png_image pngImage{};
  pngImage.version = PNG_IMAGE_VERSION;

  if (!png_image_begin_read_from_file(&pngImage, path.string().c_str())) {
    throw std::runtime_error("failed to read PNG: " + path.string() + ": " +
                             pngImage.message);
  }
  pngImage.format = PNG_FORMAT_RGBA;

  Image image;
  image.width = pngImage.width;
  image.height = pngImage.height;
  image.rgba.resize(static_cast<std::size_t>(PNG_IMAGE_SIZE(pngImage)));

  if (!png_image_finish_read(&pngImage, nullptr, image.rgba.data(), 0,
                             nullptr)) {
    const std::string message = pngImage.message;
    png_image_free(&pngImage);
    throw std::runtime_error("failed to decode PNG: " + path.string() + ": " +
                             message);
  }
  png_image_free(&pngImage);
  return image;
}

void writePng(const std::filesystem::path &path, const Image &image) {
  png_image pngImage{};
  pngImage.version = PNG_IMAGE_VERSION;
  pngImage.width = image.width;
  pngImage.height = image.height;
  pngImage.format = PNG_FORMAT_RGBA;

  std::filesystem::create_directories(path.parent_path());
  if (!png_image_write_to_file(&pngImage, path.string().c_str(), 0,
                               image.rgba.data(), 0, nullptr)) {
    const std::string message = pngImage.message;
    png_image_free(&pngImage);
    throw std::runtime_error("failed to write PNG: " + path.string() + ": " +
                             message);
  }
  png_image_free(&pngImage);
}

namespace {

std::vector<float> toLuminance(const Image &image) {
  std::vector<float> luma(static_cast<std::size_t>(image.width) * image.height);
  for (std::size_t i = 0; i < luma.size(); ++i) {
    const std::uint8_t r = image.rgba[i * 4 + 0];
    const std::uint8_t g = image.rgba[i * 4 + 1];
    const std::uint8_t b = image.rgba[i * 4 + 2];
    luma[i] = 0.299F * static_cast<float>(r) + 0.587F * static_cast<float>(g) +
              0.114F * static_cast<float>(b);
  }
  return luma;
}

} // namespace

double ssim(const Image &a, const Image &b) {
  if (a.width != b.width || a.height != b.height) {
    throw std::invalid_argument("ssim requires images of equal dimensions");
  }
  if (a.width == 0 || a.height == 0) {
    return 1.0;
  }

  const auto lumaA = toLuminance(a);
  const auto lumaB = toLuminance(b);

  constexpr int kWindow = 8;
  constexpr double kC1 = (0.01 * 255.0) * (0.01 * 255.0);
  constexpr double kC2 = (0.03 * 255.0) * (0.03 * 255.0);

  double totalSsim = 0.0;
  int windowCount = 0;

  for (std::uint32_t by = 0; by < a.height; by += kWindow) {
    for (std::uint32_t bx = 0; bx < a.width; bx += kWindow) {
      const std::uint32_t x1 = std::min(bx + kWindow, a.width);
      const std::uint32_t y1 = std::min(by + kWindow, a.height);

      double meanA = 0.0;
      double meanB = 0.0;
      int n = 0;
      for (std::uint32_t y = by; y < y1; ++y) {
        for (std::uint32_t x = bx; x < x1; ++x) {
          const std::size_t idx = static_cast<std::size_t>(y) * a.width + x;
          meanA += lumaA[idx];
          meanB += lumaB[idx];
          ++n;
        }
      }
      meanA /= n;
      meanB /= n;

      double varA = 0.0;
      double varB = 0.0;
      double covAB = 0.0;
      for (std::uint32_t y = by; y < y1; ++y) {
        for (std::uint32_t x = bx; x < x1; ++x) {
          const std::size_t idx = static_cast<std::size_t>(y) * a.width + x;
          const double da = lumaA[idx] - meanA;
          const double db = lumaB[idx] - meanB;
          varA += da * da;
          varB += db * db;
          covAB += da * db;
        }
      }
      varA /= n;
      varB /= n;
      covAB /= n;

      const double numerator =
          (2.0 * meanA * meanB + kC1) * (2.0 * covAB + kC2);
      const double denominator =
          (meanA * meanA + meanB * meanB + kC1) * (varA + varB + kC2);
      totalSsim += denominator != 0.0 ? numerator / denominator : 1.0;
      ++windowCount;
    }
  }

  return windowCount > 0 ? totalSsim / windowCount : 1.0;
}

double pixelDifferenceRatio(const Image &a, const Image &b,
                            std::uint8_t tolerance) {
  if (a.width != b.width || a.height != b.height) {
    throw std::invalid_argument(
        "pixelDifferenceRatio requires images of equal dimensions");
  }
  if (a.rgba.empty()) {
    return 0.0;
  }

  const std::size_t pixelCount = static_cast<std::size_t>(a.width) * a.height;
  std::size_t differing = 0;
  for (std::size_t i = 0; i < pixelCount; ++i) {
    bool differs = false;
    for (int c = 0; c < 4; ++c) {
      const int diff = std::abs(
          static_cast<int>(a.rgba[i * 4 + static_cast<std::size_t>(c)]) -
          static_cast<int>(b.rgba[i * 4 + static_cast<std::size_t>(c)]));
      if (diff > tolerance) {
        differs = true;
        break;
      }
    }
    if (differs)
      ++differing;
  }
  return static_cast<double>(differing) / static_cast<double>(pixelCount);
}

} // namespace mivw::testing
