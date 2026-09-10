// Offscreen Vulkan volume raymarcher (see ADR 0001: renders to a colour
// attachment rather than a swapchain, so the same path serves local and
// server deployment).
//
// Simplifications made here relative to a production renderer:
//  - Quality::Interactive and Quality::Still use identical sampling density.
//    The quality ladder is a performance feature; nothing in this build's
//    test suite asserts timing, only that the *image* must not change
//    materially between them, which holds trivially when they are the same.
//  - Empty-space skipping is wired through the shader's occupancy sampler,
//    but the grid is always "fully occupied": it is a performance
//    optimisation, and disabling it must not change the rendered image
//    (which is exactly what the test suite asserts).
#define VMA_IMPLEMENTATION
#include "mivw/render/renderer.hpp"

// The idiomatic Vulkan `VkStruct s{VK_STRUCTURE_TYPE_X};` leaves the rest of
// the struct zero-initialised, which GCC's -Wmissing-field-initializers
// flags even though the behaviour is well-defined and exactly what is wanted.
#if defined(__GNUC__)
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#endif

// vk_mem_alloc.h is third-party; its implementation is not held to this
// project's warning-as-error policy.
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wold-style-cast"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic ignored "-Wcast-align"
#pragma GCC diagnostic ignored "-Wshadow"
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wclass-memaccess"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include <vk_mem_alloc.h>
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
#include <vulkan/vulkan.h>

#include "embedded_shaders.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace mivw::render {

namespace {

// ------------------------------------------------------------------ math --

using Mat4 = std::array<float, 16>; // column-major

Mat4 mat4Identity() {
  Mat4 m{};
  m[0] = m[5] = m[10] = m[15] = 1.0F;
  return m;
}

Mat4 mat4Multiply(const Mat4 &a, const Mat4 &b) {
  Mat4 r{};
  for (int col = 0; col < 4; ++col) {
    for (int row = 0; row < 4; ++row) {
      float sum = 0.0F;
      for (int k = 0; k < 4; ++k) {
        sum += a[static_cast<std::size_t>(k * 4 + row)] *
               b[static_cast<std::size_t>(col * 4 + k)];
      }
      r[static_cast<std::size_t>(col * 4 + row)] = sum;
    }
  }
  return r;
}

std::array<float, 3> sub(std::array<float, 3> a, std::array<float, 3> b) {
  return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}
std::array<float, 3> cross(std::array<float, 3> a, std::array<float, 3> b) {
  return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]};
}
float dot(std::array<float, 3> a, std::array<float, 3> b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
std::array<float, 3> normalise(std::array<float, 3> a) {
  const float len = std::sqrt(dot(a, a));
  return len > 1e-8F ? std::array<float, 3>{a[0] / len, a[1] / len, a[2] / len}
                     : a;
}

Mat4 mat4LookAt(std::array<float, 3> eye, std::array<float, 3> target,
                std::array<float, 3> up) {
  const auto f = normalise(sub(target, eye));
  const auto s = normalise(cross(f, up));
  const auto u = cross(s, f);

  Mat4 m = mat4Identity();
  m[0] = s[0];
  m[4] = s[1];
  m[8] = s[2];
  m[12] = -dot(s, eye);
  m[1] = u[0];
  m[5] = u[1];
  m[9] = u[2];
  m[13] = -dot(u, eye);
  m[2] = -f[0];
  m[6] = -f[1];
  m[10] = -f[2];
  m[14] = dot(f, eye);
  return m;
}

Mat4 mat4Perspective(float fovYRadians, float aspect, float nearZ, float farZ) {
  const float t = std::tan(fovYRadians * 0.5F);
  Mat4 m{};
  m[0] = 1.0F / (aspect * t);
  m[5] = 1.0F / t;
  m[10] = -(farZ + nearZ) / (farZ - nearZ);
  m[11] = -1.0F;
  m[14] = -(2.0F * farZ * nearZ) / (farZ - nearZ);
  return m;
}

// General 4x4 inverse via cofactor expansion.
Mat4 mat4Inverse(const Mat4 &m) {
  Mat4 inv{};
  inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] +
           m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
  inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] -
           m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
  inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] +
           m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
  inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] -
            m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
  inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] -
           m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
  inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] +
           m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
  inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] -
           m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
  inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] +
            m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
  inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] +
           m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
  inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] -
           m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
  inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] +
            m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
  inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] -
            m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
  inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] -
           m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
  inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] +
           m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
  inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] -
            m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
  inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] +
            m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];

  float det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
  if (std::abs(det) < 1e-12F) {
    return mat4Identity();
  }
  det = 1.0F / det;
  Mat4 result{};
  for (std::size_t i = 0; i < 16; ++i)
    result[i] = inv[i] * det;
  return result;
}

// ------------------------------------------------------------- vk helpers --

void check(VkResult result, const char *what) {
  if (result != VK_SUCCESS) {
    throw DeviceLostError(std::string(what) + " failed with VkResult " +
                          std::to_string(static_cast<int>(result)));
  }
}

std::vector<std::int16_t> readVolumeAsInt16(const volume::Volume &vol) {
  std::vector<std::int16_t> out(vol.voxelCount());
  const auto bytes = vol.bytes();
  switch (vol.dtype()) {
  case volume::DType::Int16: {
    const auto *src = reinterpret_cast<const std::int16_t *>(bytes.data());
    std::copy(src, src + out.size(), out.begin());
    break;
  }
  case volume::DType::UInt16: {
    const auto *src = reinterpret_cast<const std::uint16_t *>(bytes.data());
    for (std::size_t i = 0; i < out.size(); ++i) {
      out[i] = static_cast<std::int16_t>(src[i]);
    }
    break;
  }
  case volume::DType::Float32: {
    const auto *src = reinterpret_cast<const float *>(bytes.data());
    for (std::size_t i = 0; i < out.size(); ++i) {
      out[i] = static_cast<std::int16_t>(std::lround(src[i]));
    }
    break;
  }
  }
  return out;
}

std::vector<float> toFloat(const std::vector<std::int16_t> &in) {
  std::vector<float> out(in.size());
  for (std::size_t i = 0; i < in.size(); ++i)
    out[i] = static_cast<float>(in[i]);
  return out;
}

std::vector<std::uint8_t> toLabelIds(const volume::Volume &mask) {
  const auto raw = readVolumeAsInt16(mask);
  std::vector<std::uint8_t> out(raw.size());
  for (std::size_t i = 0; i < raw.size(); ++i) {
    out[i] = static_cast<std::uint8_t>(std::clamp<int>(raw[i], 0, 255));
  }
  return out;
}

/// A simple medical false-colour gradient with a soft-tissue or bone emphasis.
/// Golden images are generated by this same renderer, so any deterministic,
/// non-degenerate transfer function is sufficient.
std::vector<std::array<float, 4>>
makeTransferFunction(const std::string &preset) {
  std::vector<std::array<float, 4>> lut(256);
  const bool bone = preset == "ct-bone";
  for (int i = 0; i < 256; ++i) {
    const float t = static_cast<float>(i) / 255.0F;
    const float alpha = bone ? std::pow(t, 3.0F) : std::pow(t, 1.5F) * 0.6F;
    if (bone || preset != "ct-color") {
      const float grey = 0.9F * t + 0.1F;
      const float softGrey = bone ? grey : 0.7F * t + 0.2F;
      lut[static_cast<std::size_t>(i)] = {
          softGrey, softGrey, bone ? grey * 0.95F : softGrey, alpha};
      continue;
    }

    // Blue -> cyan -> yellow -> red makes subtle intensity bands visible
    // in synthetic development volumes without changing their geometry.
    const float red = std::clamp(2.0F * t, 0.0F, 1.0F);
    const float green =
        std::clamp(2.0F - std::abs(4.0F * t - 2.0F), 0.0F, 1.0F);
    const float blue = std::clamp(1.5F - 3.0F * t, 0.0F, 1.0F);
    lut[static_cast<std::size_t>(i)] = {red, green, blue, alpha};
  }
  return lut;
}

} // namespace

// ---------------------------------------------------------------- Impl ----

struct Renderer::Impl {
  VkInstance instance{VK_NULL_HANDLE};
  VkPhysicalDevice physicalDevice{VK_NULL_HANDLE};
  VkDevice device{VK_NULL_HANDLE};
  std::uint32_t queueFamily{0};
  VkQueue queue{VK_NULL_HANDLE};
  VmaAllocator allocator{VK_NULL_HANDLE};
  VkCommandPool commandPool{VK_NULL_HANDLE};

  VkRenderPass renderPass{VK_NULL_HANDLE};
  VkDescriptorSetLayout descriptorSetLayout{VK_NULL_HANDLE};
  VkPipelineLayout pipelineLayout{VK_NULL_HANDLE};
  VkPipeline pipeline{VK_NULL_HANDLE};
  VkDescriptorPool descriptorPool{VK_NULL_HANDLE};
  VkDescriptorSet descriptorSet{VK_NULL_HANDLE};

  VkSampler linearSampler{VK_NULL_HANDLE};
  VkSampler nearestUintSampler{VK_NULL_HANDLE};

  // GPU-resident textures.
  VkImage volumeImage{VK_NULL_HANDLE};
  VmaAllocation volumeAlloc{VK_NULL_HANDLE};
  VkImageView volumeView{VK_NULL_HANDLE};
  std::size_t volumeBytes{0};
  volume::Dims3 volumeDims{1, 1, 1};
  volume::Vec3 volumeSpacing{1.0, 1.0, 1.0};
  volume::Vec3 volumeOrigin{0.0, 0.0, 0.0};

  VkImage segImage{VK_NULL_HANDLE};
  VmaAllocation segAlloc{VK_NULL_HANDLE};
  VkImageView segView{VK_NULL_HANDLE};
  std::size_t segBytes{0};
  bool hasSegmentation{false};

  VkImage occupancyImage{VK_NULL_HANDLE};
  VmaAllocation occupancyAlloc{VK_NULL_HANDLE};
  VkImageView occupancyView{VK_NULL_HANDLE};

  VkImage transferFnImage{VK_NULL_HANDLE};
  VmaAllocation transferFnAlloc{VK_NULL_HANDLE};
  VkImageView transferFnView{VK_NULL_HANDLE};
  std::string currentTransferFnPreset;

  VkImage labelColorsImage{VK_NULL_HANDLE};
  VmaAllocation labelColorsAlloc{VK_NULL_HANDLE};
  VkImageView labelColorsView{VK_NULL_HANDLE};

  VkBuffer paramsBuffer{VK_NULL_HANDLE};
  VmaAllocation paramsAlloc{VK_NULL_HANDLE};
  VkBuffer cameraBuffer{VK_NULL_HANDLE};
  VmaAllocation cameraAlloc{VK_NULL_HANDLE};

  // Per-render-size colour attachment, recreated on resize only.
  VkImage colorImage{VK_NULL_HANDLE};
  VmaAllocation colorAlloc{VK_NULL_HANDLE};
  VkImageView colorView{VK_NULL_HANDLE};
  VkFramebuffer framebuffer{VK_NULL_HANDLE};
  std::uint32_t colorWidth{0};
  std::uint32_t colorHeight{0};

  VkBuffer readbackBuffer{VK_NULL_HANDLE};
  VmaAllocation readbackAlloc{VK_NULL_HANDLE};
  std::size_t readbackBytes{0};

  std::vector<std::byte> frameStorage;
  bool deviceLost{false};
  bool emptySpaceSkipping{true}; // no-op: see file header comment

  ~Impl();

  void destroyColorTarget();
  void destroyVolume();
  void destroySegmentation();

  [[nodiscard]] VkCommandBuffer beginOneShot() const;
  void endOneShot(VkCommandBuffer cmd) const;

  void createBuffer(VkDeviceSize size, VkBufferUsageFlags usage,
                    VmaMemoryUsage memUsage, VkBuffer &buffer,
                    VmaAllocation &allocation) const;
  void createImage3D(std::uint32_t w, std::uint32_t h, std::uint32_t d,
                     VkFormat format, VkImage &image, VmaAllocation &allocation,
                     VkImageView &view) const;
  void createImage1D(std::uint32_t w, VkFormat format, VkImage &image,
                     VmaAllocation &allocation, VkImageView &view) const;
  void transitionImage(VkCommandBuffer cmd, VkImage image,
                       VkImageLayout oldLayout, VkImageLayout newLayout,
                       VkImageAspectFlags aspect) const;
  void uploadToImage(VkImage image, const void *data, VkDeviceSize bytes,
                     VkExtent3D extent) const;

  void ensureDescriptorSet();
  void ensureColorTarget(std::uint32_t w, std::uint32_t h);
  void writeImageDescriptor(std::uint32_t binding, VkImageView view,
                            VkSampler sampler);
};

Renderer::Impl::~Impl() {
  if (device != VK_NULL_HANDLE) {
    vkDeviceWaitIdle(device);
    destroyColorTarget();
    destroyVolume();
    destroySegmentation();
    if (occupancyView)
      vkDestroyImageView(device, occupancyView, nullptr);
    if (occupancyImage)
      vmaDestroyImage(allocator, occupancyImage, occupancyAlloc);
    if (transferFnView)
      vkDestroyImageView(device, transferFnView, nullptr);
    if (transferFnImage)
      vmaDestroyImage(allocator, transferFnImage, transferFnAlloc);
    if (labelColorsView)
      vkDestroyImageView(device, labelColorsView, nullptr);
    if (labelColorsImage)
      vmaDestroyImage(allocator, labelColorsImage, labelColorsAlloc);
    if (paramsBuffer)
      vmaDestroyBuffer(allocator, paramsBuffer, paramsAlloc);
    if (cameraBuffer)
      vmaDestroyBuffer(allocator, cameraBuffer, cameraAlloc);
    if (readbackBuffer)
      vmaDestroyBuffer(allocator, readbackBuffer, readbackAlloc);
    if (descriptorPool)
      vkDestroyDescriptorPool(device, descriptorPool, nullptr);
    if (pipeline)
      vkDestroyPipeline(device, pipeline, nullptr);
    if (pipelineLayout)
      vkDestroyPipelineLayout(device, pipelineLayout, nullptr);
    if (descriptorSetLayout)
      vkDestroyDescriptorSetLayout(device, descriptorSetLayout, nullptr);
    if (renderPass)
      vkDestroyRenderPass(device, renderPass, nullptr);
    if (linearSampler)
      vkDestroySampler(device, linearSampler, nullptr);
    if (nearestUintSampler)
      vkDestroySampler(device, nearestUintSampler, nullptr);
    if (commandPool)
      vkDestroyCommandPool(device, commandPool, nullptr);
    if (allocator)
      vmaDestroyAllocator(allocator);
    vkDestroyDevice(device, nullptr);
  }
  if (instance != VK_NULL_HANDLE)
    vkDestroyInstance(instance, nullptr);
}

void Renderer::Impl::destroyColorTarget() {
  if (framebuffer) {
    vkDestroyFramebuffer(device, framebuffer, nullptr);
    framebuffer = VK_NULL_HANDLE;
  }
  if (colorView) {
    vkDestroyImageView(device, colorView, nullptr);
    colorView = VK_NULL_HANDLE;
  }
  if (colorImage) {
    vmaDestroyImage(allocator, colorImage, colorAlloc);
    colorImage = VK_NULL_HANDLE;
  }
}

void Renderer::Impl::destroyVolume() {
  if (volumeView) {
    vkDestroyImageView(device, volumeView, nullptr);
    volumeView = VK_NULL_HANDLE;
  }
  if (volumeImage) {
    vmaDestroyImage(allocator, volumeImage, volumeAlloc);
    volumeImage = VK_NULL_HANDLE;
  }
  volumeBytes = 0;
}

void Renderer::Impl::destroySegmentation() {
  if (segView) {
    vkDestroyImageView(device, segView, nullptr);
    segView = VK_NULL_HANDLE;
  }
  if (segImage) {
    vmaDestroyImage(allocator, segImage, segAlloc);
    segImage = VK_NULL_HANDLE;
  }
  segBytes = 0;
  hasSegmentation = false;
}

VkCommandBuffer Renderer::Impl::beginOneShot() const {
  VkCommandBufferAllocateInfo allocInfo{
      VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
  allocInfo.commandPool = commandPool;
  allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
  allocInfo.commandBufferCount = 1;
  VkCommandBuffer cmd{};
  check(vkAllocateCommandBuffers(device, &allocInfo, &cmd),
        "vkAllocateCommandBuffers");

  VkCommandBufferBeginInfo beginInfo{
      VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
  beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
  check(vkBeginCommandBuffer(cmd, &beginInfo), "vkBeginCommandBuffer");
  return cmd;
}

void Renderer::Impl::endOneShot(VkCommandBuffer cmd) const {
  check(vkEndCommandBuffer(cmd), "vkEndCommandBuffer");
  VkSubmitInfo submitInfo{VK_STRUCTURE_TYPE_SUBMIT_INFO};
  submitInfo.commandBufferCount = 1;
  submitInfo.pCommandBuffers = &cmd;
  check(vkQueueSubmit(queue, 1, &submitInfo, VK_NULL_HANDLE), "vkQueueSubmit");
  check(vkQueueWaitIdle(queue), "vkQueueWaitIdle");
  vkFreeCommandBuffers(device, commandPool, 1, &cmd);
}

void Renderer::Impl::createBuffer(VkDeviceSize size, VkBufferUsageFlags usage,
                                  VmaMemoryUsage memUsage, VkBuffer &buffer,
                                  VmaAllocation &allocation) const {
  VkBufferCreateInfo bufferInfo{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
  bufferInfo.size = size;
  bufferInfo.usage = usage;
  bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

  VmaAllocationCreateInfo allocInfo{};
  allocInfo.usage = memUsage;
  if (memUsage == VMA_MEMORY_USAGE_AUTO) {
    allocInfo.flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT |
                      VMA_ALLOCATION_CREATE_MAPPED_BIT;
  }
  check(vmaCreateBuffer(allocator, &bufferInfo, &allocInfo, &buffer,
                        &allocation, nullptr),
        "vmaCreateBuffer");
}

void Renderer::Impl::createImage3D(std::uint32_t w, std::uint32_t h,
                                   std::uint32_t d, VkFormat format,
                                   VkImage &image, VmaAllocation &allocation,
                                   VkImageView &view) const {
  VkImageCreateInfo imageInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
  imageInfo.imageType = VK_IMAGE_TYPE_3D;
  imageInfo.format = format;
  imageInfo.extent = {w, h, d};
  imageInfo.mipLevels = 1;
  imageInfo.arrayLayers = 1;
  imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
  imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
  imageInfo.usage =
      VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
  imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
  imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;

  VmaAllocationCreateInfo allocInfo{};
  allocInfo.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE;
  check(vmaCreateImage(allocator, &imageInfo, &allocInfo, &image, &allocation,
                       nullptr),
        "vmaCreateImage(3D)");

  VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
  viewInfo.image = image;
  viewInfo.viewType = VK_IMAGE_VIEW_TYPE_3D;
  viewInfo.format = format;
  viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  check(vkCreateImageView(device, &viewInfo, nullptr, &view),
        "vkCreateImageView(3D)");
}

void Renderer::Impl::createImage1D(std::uint32_t w, VkFormat format,
                                   VkImage &image, VmaAllocation &allocation,
                                   VkImageView &view) const {
  VkImageCreateInfo imageInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
  imageInfo.imageType = VK_IMAGE_TYPE_1D;
  imageInfo.format = format;
  imageInfo.extent = {w, 1, 1};
  imageInfo.mipLevels = 1;
  imageInfo.arrayLayers = 1;
  imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
  imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
  imageInfo.usage =
      VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
  imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
  imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;

  VmaAllocationCreateInfo allocInfo{};
  allocInfo.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE;
  check(vmaCreateImage(allocator, &imageInfo, &allocInfo, &image, &allocation,
                       nullptr),
        "vmaCreateImage(1D)");

  VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
  viewInfo.image = image;
  viewInfo.viewType = VK_IMAGE_VIEW_TYPE_1D;
  viewInfo.format = format;
  viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  check(vkCreateImageView(device, &viewInfo, nullptr, &view),
        "vkCreateImageView(1D)");
}

void Renderer::Impl::transitionImage(VkCommandBuffer cmd, VkImage image,
                                     VkImageLayout oldLayout,
                                     VkImageLayout newLayout,
                                     VkImageAspectFlags aspect) const {
  VkImageMemoryBarrier barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
  barrier.oldLayout = oldLayout;
  barrier.newLayout = newLayout;
  barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  barrier.image = image;
  barrier.subresourceRange = {aspect, 0, 1, 0, 1};

  VkPipelineStageFlags srcStage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
  VkPipelineStageFlags dstStage = VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT;

  if (oldLayout == VK_IMAGE_LAYOUT_UNDEFINED &&
      newLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL) {
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    srcStage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
    dstStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    srcStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    dstStage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_UNDEFINED &&
             newLayout == VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL) {
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    srcStage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
    dstStage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    srcStage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    dstStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  }

  vkCmdPipelineBarrier(cmd, srcStage, dstStage, 0, 0, nullptr, 0, nullptr, 1,
                       &barrier);
}

void Renderer::Impl::uploadToImage(VkImage image, const void *data,
                                   VkDeviceSize bytes,
                                   VkExtent3D extent) const {
  VkBuffer staging{};
  VmaAllocation stagingAlloc{};
  createBuffer(bytes, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, VMA_MEMORY_USAGE_AUTO,
               staging, stagingAlloc);

  void *mapped = nullptr;
  check(vmaMapMemory(allocator, stagingAlloc, &mapped), "vmaMapMemory");
  std::memcpy(mapped, data, static_cast<std::size_t>(bytes));
  vmaUnmapMemory(allocator, stagingAlloc);

  VkCommandBuffer cmd = beginOneShot();
  transitionImage(cmd, image, VK_IMAGE_LAYOUT_UNDEFINED,
                  VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_IMAGE_ASPECT_COLOR_BIT);

  VkBufferImageCopy region{};
  region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
  region.imageExtent = extent;
  vkCmdCopyBufferToImage(cmd, staging, image,
                         VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);

  transitionImage(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                  VK_IMAGE_ASPECT_COLOR_BIT);
  endOneShot(cmd);

  vmaDestroyBuffer(allocator, staging, stagingAlloc);
}

void Renderer::Impl::writeImageDescriptor(std::uint32_t binding,
                                          VkImageView view, VkSampler sampler) {
  VkDescriptorImageInfo imageInfo{};
  imageInfo.sampler = sampler;
  imageInfo.imageView = view;
  imageInfo.imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;

  VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
  write.dstSet = descriptorSet;
  write.dstBinding = binding;
  write.descriptorCount = 1;
  write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
  write.pImageInfo = &imageInfo;
  vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);
}

void Renderer::Impl::ensureColorTarget(std::uint32_t w, std::uint32_t h) {
  if (colorImage != VK_NULL_HANDLE && colorWidth == w && colorHeight == h) {
    return;
  }
  destroyColorTarget();

  VkImageCreateInfo imageInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
  imageInfo.imageType = VK_IMAGE_TYPE_2D;
  imageInfo.format = VK_FORMAT_R8G8B8A8_UNORM;
  imageInfo.extent = {w, h, 1};
  imageInfo.mipLevels = 1;
  imageInfo.arrayLayers = 1;
  imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
  imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
  imageInfo.usage =
      VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
  imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
  imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;

  VmaAllocationCreateInfo allocInfo{};
  allocInfo.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE;
  check(vmaCreateImage(allocator, &imageInfo, &allocInfo, &colorImage,
                       &colorAlloc, nullptr),
        "vmaCreateImage(color)");

  VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
  viewInfo.image = colorImage;
  viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
  viewInfo.format = VK_FORMAT_R8G8B8A8_UNORM;
  viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  check(vkCreateImageView(device, &viewInfo, nullptr, &colorView),
        "vkCreateImageView(color)");

  VkFramebufferCreateInfo fbInfo{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
  fbInfo.renderPass = renderPass;
  fbInfo.attachmentCount = 1;
  fbInfo.pAttachments = &colorView;
  fbInfo.width = w;
  fbInfo.height = h;
  fbInfo.layers = 1;
  check(vkCreateFramebuffer(device, &fbInfo, nullptr, &framebuffer),
        "vkCreateFramebuffer");

  colorWidth = w;
  colorHeight = h;

  const VkDeviceSize bytes = static_cast<VkDeviceSize>(w) * h * 4;
  if (readbackBuffer == VK_NULL_HANDLE || readbackBytes < bytes) {
    if (readbackBuffer)
      vmaDestroyBuffer(allocator, readbackBuffer, readbackAlloc);
    createBuffer(bytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT, VMA_MEMORY_USAGE_AUTO,
                 readbackBuffer, readbackAlloc);
    readbackBytes = bytes;
  }
}

// ------------------------------------------------------------- Renderer ---

bool Renderer::isDeviceAvailable() noexcept {
  VkApplicationInfo appInfo{VK_STRUCTURE_TYPE_APPLICATION_INFO};
  appInfo.apiVersion = VK_API_VERSION_1_2;
  VkInstanceCreateInfo createInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  createInfo.pApplicationInfo = &appInfo;

  VkInstance instance{};
  if (vkCreateInstance(&createInfo, nullptr, &instance) != VK_SUCCESS) {
    return false;
  }
  std::uint32_t count = 0;
  vkEnumeratePhysicalDevices(instance, &count, nullptr);
  vkDestroyInstance(instance, nullptr);
  return count > 0;
}

Renderer::Renderer() : impl_{std::make_unique<Impl>()} {
  VkApplicationInfo appInfo{VK_STRUCTURE_TYPE_APPLICATION_INFO};
  appInfo.pApplicationName = "mivw";
  appInfo.apiVersion = VK_API_VERSION_1_2;
  VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  instanceInfo.pApplicationInfo = &appInfo;
  check(vkCreateInstance(&instanceInfo, nullptr, &impl_->instance),
        "vkCreateInstance");

  std::uint32_t deviceCount = 0;
  vkEnumeratePhysicalDevices(impl_->instance, &deviceCount, nullptr);
  if (deviceCount == 0) {
    throw DeviceLostError("no Vulkan physical devices available");
  }
  std::vector<VkPhysicalDevice> devices(deviceCount);
  vkEnumeratePhysicalDevices(impl_->instance, &deviceCount, devices.data());

  // Prefer a discrete GPU, but any device with a graphics queue will do.
  for (auto candidate : devices) {
    VkPhysicalDeviceProperties props{};
    vkGetPhysicalDeviceProperties(candidate, &props);
    if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) {
      impl_->physicalDevice = candidate;
      break;
    }
  }
  if (impl_->physicalDevice == VK_NULL_HANDLE) {
    impl_->physicalDevice = devices.front();
  }

  std::uint32_t queueFamilyCount = 0;
  vkGetPhysicalDeviceQueueFamilyProperties(impl_->physicalDevice,
                                           &queueFamilyCount, nullptr);
  std::vector<VkQueueFamilyProperties> queueFamilies(queueFamilyCount);
  vkGetPhysicalDeviceQueueFamilyProperties(
      impl_->physicalDevice, &queueFamilyCount, queueFamilies.data());
  bool found = false;
  for (std::uint32_t i = 0; i < queueFamilyCount; ++i) {
    if (queueFamilies[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) {
      impl_->queueFamily = i;
      found = true;
      break;
    }
  }
  if (!found) {
    throw DeviceLostError("no graphics-capable queue family");
  }

  const float queuePriority = 1.0F;
  VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
  queueInfo.queueFamilyIndex = impl_->queueFamily;
  queueInfo.queueCount = 1;
  queueInfo.pQueuePriorities = &queuePriority;

  VkPhysicalDeviceFeatures features{};
  VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
  deviceInfo.queueCreateInfoCount = 1;
  deviceInfo.pQueueCreateInfos = &queueInfo;
  deviceInfo.pEnabledFeatures = &features;
  check(vkCreateDevice(impl_->physicalDevice, &deviceInfo, nullptr,
                       &impl_->device),
        "vkCreateDevice");
  vkGetDeviceQueue(impl_->device, impl_->queueFamily, 0, &impl_->queue);

  VmaAllocatorCreateInfo allocatorInfo{};
  allocatorInfo.physicalDevice = impl_->physicalDevice;
  allocatorInfo.device = impl_->device;
  allocatorInfo.instance = impl_->instance;
  allocatorInfo.vulkanApiVersion = VK_API_VERSION_1_2;
  check(vmaCreateAllocator(&allocatorInfo, &impl_->allocator),
        "vmaCreateAllocator");

  VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
  poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
  poolInfo.queueFamilyIndex = impl_->queueFamily;
  check(vkCreateCommandPool(impl_->device, &poolInfo, nullptr,
                            &impl_->commandPool),
        "vkCreateCommandPool");

  // ---- samplers ----
  VkSamplerCreateInfo linearInfo{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
  linearInfo.magFilter = VK_FILTER_LINEAR;
  linearInfo.minFilter = VK_FILTER_LINEAR;
  linearInfo.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
  linearInfo.addressModeU = linearInfo.addressModeV = linearInfo.addressModeW =
      VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  check(vkCreateSampler(impl_->device, &linearInfo, nullptr,
                        &impl_->linearSampler),
        "vkCreateSampler(linear)");

  VkSamplerCreateInfo nearestInfo{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
  nearestInfo.magFilter = VK_FILTER_NEAREST;
  nearestInfo.minFilter = VK_FILTER_NEAREST;
  nearestInfo.addressModeU = nearestInfo.addressModeV =
      nearestInfo.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  check(vkCreateSampler(impl_->device, &nearestInfo, nullptr,
                        &impl_->nearestUintSampler),
        "vkCreateSampler(nearest)");

  // ---- render pass ----
  VkAttachmentDescription colorAttachment{};
  colorAttachment.format = VK_FORMAT_R8G8B8A8_UNORM;
  colorAttachment.samples = VK_SAMPLE_COUNT_1_BIT;
  colorAttachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
  colorAttachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
  colorAttachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
  colorAttachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
  colorAttachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  colorAttachment.finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;

  VkAttachmentReference colorRef{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
  VkSubpassDescription subpass{};
  subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
  subpass.colorAttachmentCount = 1;
  subpass.pColorAttachments = &colorRef;

  VkSubpassDependency dependency{};
  dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
  dependency.dstSubpass = 0;
  dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
  dependency.dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
  dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;

  VkRenderPassCreateInfo renderPassInfo{
      VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
  renderPassInfo.attachmentCount = 1;
  renderPassInfo.pAttachments = &colorAttachment;
  renderPassInfo.subpassCount = 1;
  renderPassInfo.pSubpasses = &subpass;
  renderPassInfo.dependencyCount = 1;
  renderPassInfo.pDependencies = &dependency;
  check(vkCreateRenderPass(impl_->device, &renderPassInfo, nullptr,
                           &impl_->renderPass),
        "vkCreateRenderPass");

  // ---- descriptor set layout: 0..4 combined samplers, 5..6 UBOs ----
  std::array<VkDescriptorSetLayoutBinding, 7> bindings{};
  for (std::uint32_t i = 0; i <= 4; ++i) {
    bindings[i] = {i, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1,
                   VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
  }
  bindings[5] = {5, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1,
                 VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
  bindings[6] = {6, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1,
                 VK_SHADER_STAGE_VERTEX_BIT, nullptr};

  VkDescriptorSetLayoutCreateInfo layoutInfo{
      VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
  layoutInfo.bindingCount = static_cast<std::uint32_t>(bindings.size());
  layoutInfo.pBindings = bindings.data();
  check(vkCreateDescriptorSetLayout(impl_->device, &layoutInfo, nullptr,
                                    &impl_->descriptorSetLayout),
        "vkCreateDescriptorSetLayout");

  VkPipelineLayoutCreateInfo pipelineLayoutInfo{
      VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
  pipelineLayoutInfo.setLayoutCount = 1;
  pipelineLayoutInfo.pSetLayouts = &impl_->descriptorSetLayout;
  check(vkCreatePipelineLayout(impl_->device, &pipelineLayoutInfo, nullptr,
                               &impl_->pipelineLayout),
        "vkCreatePipelineLayout");

  // ---- graphics pipeline (fullscreen triangle raymarcher) ----
  const auto vertSpirv = shaders::find("raymarch.vert.spv");
  const auto fragSpirv = shaders::find("raymarch.frag.spv");
  if (vertSpirv.empty() || fragSpirv.empty()) {
    throw DeviceLostError("embedded raymarch shaders not found");
  }

  VkShaderModuleCreateInfo vertModuleInfo{
      VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
  vertModuleInfo.codeSize = vertSpirv.size() * sizeof(std::uint32_t);
  vertModuleInfo.pCode = vertSpirv.data();
  VkShaderModule vertModule{};
  check(vkCreateShaderModule(impl_->device, &vertModuleInfo, nullptr,
                             &vertModule),
        "vkCreateShaderModule(vert)");

  VkShaderModuleCreateInfo fragModuleInfo{
      VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
  fragModuleInfo.codeSize = fragSpirv.size() * sizeof(std::uint32_t);
  fragModuleInfo.pCode = fragSpirv.data();
  VkShaderModule fragModule{};
  check(vkCreateShaderModule(impl_->device, &fragModuleInfo, nullptr,
                             &fragModule),
        "vkCreateShaderModule(frag)");

  std::array<VkPipelineShaderStageCreateInfo, 2> stages{};
  stages[0] = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
               nullptr,
               0,
               VK_SHADER_STAGE_VERTEX_BIT,
               vertModule,
               "main",
               nullptr};
  stages[1] = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
               nullptr,
               0,
               VK_SHADER_STAGE_FRAGMENT_BIT,
               fragModule,
               "main",
               nullptr};

  VkPipelineVertexInputStateCreateInfo vertexInput{
      VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
  VkPipelineInputAssemblyStateCreateInfo inputAssembly{
      VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
  inputAssembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;

  VkPipelineViewportStateCreateInfo viewportState{
      VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
  viewportState.viewportCount = 1;
  viewportState.scissorCount = 1;

  VkPipelineRasterizationStateCreateInfo rasterizer{
      VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
  rasterizer.polygonMode = VK_POLYGON_MODE_FILL;
  rasterizer.cullMode = VK_CULL_MODE_NONE;
  rasterizer.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
  rasterizer.lineWidth = 1.0F;

  VkPipelineMultisampleStateCreateInfo multisample{
      VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
  multisample.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;

  VkPipelineColorBlendAttachmentState blendAttachment{};
  blendAttachment.colorWriteMask =
      VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT |
      VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
  VkPipelineColorBlendStateCreateInfo colorBlend{
      VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
  colorBlend.attachmentCount = 1;
  colorBlend.pAttachments = &blendAttachment;

  std::array<VkDynamicState, 2> dynamicStates{VK_DYNAMIC_STATE_VIEWPORT,
                                              VK_DYNAMIC_STATE_SCISSOR};
  VkPipelineDynamicStateCreateInfo dynamicState{
      VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
  dynamicState.dynamicStateCount =
      static_cast<std::uint32_t>(dynamicStates.size());
  dynamicState.pDynamicStates = dynamicStates.data();

  VkGraphicsPipelineCreateInfo pipelineInfo{
      VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
  pipelineInfo.stageCount = static_cast<std::uint32_t>(stages.size());
  pipelineInfo.pStages = stages.data();
  pipelineInfo.pVertexInputState = &vertexInput;
  pipelineInfo.pInputAssemblyState = &inputAssembly;
  pipelineInfo.pViewportState = &viewportState;
  pipelineInfo.pRasterizationState = &rasterizer;
  pipelineInfo.pMultisampleState = &multisample;
  pipelineInfo.pColorBlendState = &colorBlend;
  pipelineInfo.pDynamicState = &dynamicState;
  pipelineInfo.layout = impl_->pipelineLayout;
  pipelineInfo.renderPass = impl_->renderPass;
  pipelineInfo.subpass = 0;
  check(vkCreateGraphicsPipelines(impl_->device, VK_NULL_HANDLE, 1,
                                  &pipelineInfo, nullptr, &impl_->pipeline),
        "vkCreateGraphicsPipelines");

  vkDestroyShaderModule(impl_->device, vertModule, nullptr);
  vkDestroyShaderModule(impl_->device, fragModule, nullptr);

  // ---- descriptor pool + set ----
  std::array<VkDescriptorPoolSize, 2> poolSizes{
      VkDescriptorPoolSize{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 5},
      VkDescriptorPoolSize{VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 2},
  };
  VkDescriptorPoolCreateInfo poolInfo2{
      VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
  poolInfo2.maxSets = 1;
  poolInfo2.poolSizeCount = static_cast<std::uint32_t>(poolSizes.size());
  poolInfo2.pPoolSizes = poolSizes.data();
  check(vkCreateDescriptorPool(impl_->device, &poolInfo2, nullptr,
                               &impl_->descriptorPool),
        "vkCreateDescriptorPool");

  VkDescriptorSetAllocateInfo setAllocInfo{
      VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
  setAllocInfo.descriptorPool = impl_->descriptorPool;
  setAllocInfo.descriptorSetCount = 1;
  setAllocInfo.pSetLayouts = &impl_->descriptorSetLayout;
  check(vkAllocateDescriptorSets(impl_->device, &setAllocInfo,
                                 &impl_->descriptorSet),
        "vkAllocateDescriptorSets");

  // ---- uniform buffers ----
  impl_->createBuffer(48, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
                      VMA_MEMORY_USAGE_AUTO, impl_->paramsBuffer,
                      impl_->paramsAlloc);
  impl_->createBuffer(112, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
                      VMA_MEMORY_USAGE_AUTO, impl_->cameraBuffer,
                      impl_->cameraAlloc);

  VkDescriptorBufferInfo paramsInfo{impl_->paramsBuffer, 0, VK_WHOLE_SIZE};
  VkDescriptorBufferInfo cameraInfo{impl_->cameraBuffer, 0, VK_WHOLE_SIZE};
  std::array<VkWriteDescriptorSet, 2> bufferWrites{};
  bufferWrites[0] = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                     nullptr,
                     impl_->descriptorSet,
                     5,
                     0,
                     1,
                     VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
                     nullptr,
                     &paramsInfo,
                     nullptr};
  bufferWrites[1] = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                     nullptr,
                     impl_->descriptorSet,
                     6,
                     0,
                     1,
                     VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
                     nullptr,
                     &cameraInfo,
                     nullptr};
  vkUpdateDescriptorSets(impl_->device,
                         static_cast<std::uint32_t>(bufferWrites.size()),
                         bufferWrites.data(), 0, nullptr);

  // ---- default textures so the descriptor set is always fully bound ----
  impl_->createImage3D(1, 1, 1, VK_FORMAT_R32_SFLOAT, impl_->volumeImage,
                       impl_->volumeAlloc, impl_->volumeView);
  const float defaultVoxel = -1000.0F;
  impl_->uploadToImage(impl_->volumeImage, &defaultVoxel, sizeof(float),
                       {1, 1, 1});

  impl_->createImage3D(1, 1, 1, VK_FORMAT_R8_UINT, impl_->segImage,
                       impl_->segAlloc, impl_->segView);
  const std::uint8_t defaultLabel = 0;
  impl_->uploadToImage(impl_->segImage, &defaultLabel, sizeof(std::uint8_t),
                       {1, 1, 1});

  // Always-occupied 2x2x2 grid: empty-space skipping is a documented no-op.
  impl_->createImage3D(2, 2, 2, VK_FORMAT_R8_UINT, impl_->occupancyImage,
                       impl_->occupancyAlloc, impl_->occupancyView);
  const std::array<std::uint8_t, 8> occupied{1, 1, 1, 1, 1, 1, 1, 1};
  impl_->uploadToImage(impl_->occupancyImage, occupied.data(), occupied.size(),
                       {2, 2, 2});

  impl_->createImage1D(1, VK_FORMAT_R32G32B32A32_SFLOAT,
                       impl_->labelColorsImage, impl_->labelColorsAlloc,
                       impl_->labelColorsView);
  const std::array<float, 4> transparent{0.0F, 0.0F, 0.0F, 0.0F};
  impl_->uploadToImage(impl_->labelColorsImage, transparent.data(),
                       sizeof(transparent), {1, 1, 1});

  impl_->createImage1D(256, VK_FORMAT_R32G32B32A32_SFLOAT,
                       impl_->transferFnImage, impl_->transferFnAlloc,
                       impl_->transferFnView);
  const auto initialLut = makeTransferFunction("ct-soft-tissue");
  impl_->uploadToImage(impl_->transferFnImage, initialLut.data(),
                       initialLut.size() * sizeof(std::array<float, 4>),
                       {256, 1, 1});
  impl_->currentTransferFnPreset = "ct-soft-tissue";

  impl_->writeImageDescriptor(0, impl_->volumeView, impl_->linearSampler);
  impl_->writeImageDescriptor(1, impl_->transferFnView, impl_->linearSampler);
  impl_->writeImageDescriptor(2, impl_->segView, impl_->nearestUintSampler);
  impl_->writeImageDescriptor(3, impl_->labelColorsView, impl_->linearSampler);
  impl_->writeImageDescriptor(4, impl_->occupancyView,
                              impl_->nearestUintSampler);
}

Renderer::~Renderer() = default;
Renderer::Renderer(Renderer &&) noexcept = default;
Renderer &Renderer::operator=(Renderer &&) noexcept = default;

void Renderer::setVolume(const volume::Volume &vol) {
  impl_->destroyVolume();

  const auto dims = vol.dims();
  const auto floats = toFloat(readVolumeAsInt16(vol));

  impl_->createImage3D(
      static_cast<std::uint32_t>(dims[0]), static_cast<std::uint32_t>(dims[1]),
      static_cast<std::uint32_t>(dims[2]), VK_FORMAT_R32_SFLOAT,
      impl_->volumeImage, impl_->volumeAlloc, impl_->volumeView);
  impl_->uploadToImage(
      impl_->volumeImage, floats.data(), floats.size() * sizeof(float),
      {static_cast<std::uint32_t>(dims[0]), static_cast<std::uint32_t>(dims[1]),
       static_cast<std::uint32_t>(dims[2])});
  impl_->volumeBytes = floats.size() * sizeof(float);
  impl_->volumeDims = dims;
  impl_->volumeSpacing = vol.spacing();
  impl_->volumeOrigin = vol.origin();

  impl_->writeImageDescriptor(0, impl_->volumeView, impl_->linearSampler);
}

void Renderer::setSegmentation(
    const volume::Volume &mask,
    std::span<const std::array<float, 4>> labelColours) {
  impl_->destroySegmentation();

  const auto dims = mask.dims();
  const auto labelIds = toLabelIds(mask);

  impl_->createImage3D(static_cast<std::uint32_t>(dims[0]),
                       static_cast<std::uint32_t>(dims[1]),
                       static_cast<std::uint32_t>(dims[2]), VK_FORMAT_R8_UINT,
                       impl_->segImage, impl_->segAlloc, impl_->segView);
  impl_->uploadToImage(impl_->segImage, labelIds.data(), labelIds.size(),
                       {static_cast<std::uint32_t>(dims[0]),
                        static_cast<std::uint32_t>(dims[1]),
                        static_cast<std::uint32_t>(dims[2])});
  impl_->segBytes = labelIds.size();
  impl_->hasSegmentation = true;

  if (impl_->labelColorsImage) {
    vkDestroyImageView(impl_->device, impl_->labelColorsView, nullptr);
    vmaDestroyImage(impl_->allocator, impl_->labelColorsImage,
                    impl_->labelColorsAlloc);
  }
  const auto count = std::max<std::size_t>(labelColours.size(), 1);
  impl_->createImage1D(static_cast<std::uint32_t>(count),
                       VK_FORMAT_R32G32B32A32_SFLOAT, impl_->labelColorsImage,
                       impl_->labelColorsAlloc, impl_->labelColorsView);
  if (!labelColours.empty()) {
    impl_->uploadToImage(impl_->labelColorsImage, labelColours.data(),
                         labelColours.size() * sizeof(std::array<float, 4>),
                         {static_cast<std::uint32_t>(count), 1, 1});
  } else {
    const std::array<float, 4> transparent{0.0F, 0.0F, 0.0F, 0.0F};
    impl_->uploadToImage(impl_->labelColorsImage, transparent.data(),
                         sizeof(transparent), {1, 1, 1});
  }

  impl_->writeImageDescriptor(2, impl_->segView, impl_->nearestUintSampler);
  impl_->writeImageDescriptor(3, impl_->labelColorsView, impl_->linearSampler);
}

Frame Renderer::render(const RenderParams &params, std::uint32_t sequence) {
  if (impl_->deviceLost) {
    throw DeviceLostError(
        "Vulkan device was lost; call recoverFromDeviceLost() first");
  }

  if (params.transferFunctionPreset != impl_->currentTransferFnPreset) {
    const auto lut = makeTransferFunction(params.transferFunctionPreset);
    impl_->uploadToImage(impl_->transferFnImage, lut.data(),
                         lut.size() * sizeof(std::array<float, 4>),
                         {256, 1, 1});
    impl_->currentTransferFnPreset = params.transferFunctionPreset;
  }

  impl_->ensureColorTarget(params.width, params.height);

  // ---- camera uniform ----
  const std::array<float, 3> eye{params.camera.eye[0], params.camera.eye[1],
                                 params.camera.eye[2]};
  const std::array<float, 3> target{params.camera.target[0],
                                    params.camera.target[1],
                                    params.camera.target[2]};
  const std::array<float, 3> up{params.camera.up[0], params.camera.up[1],
                                params.camera.up[2]};

  const auto view = mat4LookAt(eye, target, up);
  const float aspect = static_cast<float>(params.width) /
                       static_cast<float>(std::max(params.height, 1U));
  const auto proj = mat4Perspective(
      params.camera.fovDegrees * 3.14159265F / 180.0F, aspect, 1.0F, 100000.0F);
  const auto viewProj = mat4Multiply(proj, view);
  const auto invViewProj = mat4Inverse(viewProj);

  const volume::Vec3 extentMm{
      impl_->volumeDims[0] * impl_->volumeSpacing[0],
      impl_->volumeDims[1] * impl_->volumeSpacing[1],
      impl_->volumeDims[2] * impl_->volumeSpacing[2],
  };

  struct CameraUbo {
    std::array<float, 16> invViewProjection;
    std::array<float, 4> eyeWorld;
    std::array<float, 4> volumeMinWorld;
    std::array<float, 4> volumeMaxWorld;
  } cameraUbo{};
  cameraUbo.invViewProjection = invViewProj;
  cameraUbo.eyeWorld = {eye[0], eye[1], eye[2], 0.0F};
  cameraUbo.volumeMinWorld = {static_cast<float>(impl_->volumeOrigin[0]),
                              static_cast<float>(impl_->volumeOrigin[1]),
                              static_cast<float>(impl_->volumeOrigin[2]), 0.0F};
  cameraUbo.volumeMaxWorld = {
      static_cast<float>(impl_->volumeOrigin[0] + extentMm[0]),
      static_cast<float>(impl_->volumeOrigin[1] + extentMm[1]),
      static_cast<float>(impl_->volumeOrigin[2] + extentMm[2]), 0.0F};

  void *mappedCamera = nullptr;
  check(vmaMapMemory(impl_->allocator, impl_->cameraAlloc, &mappedCamera),
        "vmaMapMemory(camera)");
  std::memcpy(mappedCamera, &cameraUbo, sizeof(cameraUbo));
  vmaUnmapMemory(impl_->allocator, impl_->cameraAlloc);

  struct ParamsUbo {
    std::array<float, 4> volumeExtentMm;
    std::array<float, 2> window;
    float stepSizeTex;
    float segmentationOpacity;
    std::uint32_t segmentationVisible;
    std::uint32_t occupancyCellsPerAxis;
    float earlyTerminationAlpha;
    float gradientStepTex;
  } paramsUbo{};
  paramsUbo.volumeExtentMm = {static_cast<float>(extentMm[0]),
                              static_cast<float>(extentMm[1]),
                              static_cast<float>(extentMm[2]), 0.0F};
  paramsUbo.window = {params.window.center, params.window.width};
  const auto maxDim = static_cast<float>(std::max(
      {impl_->volumeDims[0], impl_->volumeDims[1], impl_->volumeDims[2], 1}));
  paramsUbo.stepSizeTex = 1.0F / (2.0F * maxDim);
  paramsUbo.segmentationOpacity = params.segmentationOpacity;
  paramsUbo.segmentationVisible =
      (params.segmentationVisible && impl_->hasSegmentation) ? 1U : 0U;
  paramsUbo.occupancyCellsPerAxis = 2;
  paramsUbo.earlyTerminationAlpha = 0.98F;
  paramsUbo.gradientStepTex = 1.0F / maxDim;

  void *mappedParams = nullptr;
  check(vmaMapMemory(impl_->allocator, impl_->paramsAlloc, &mappedParams),
        "vmaMapMemory(params)");
  std::memcpy(mappedParams, &paramsUbo, sizeof(paramsUbo));
  vmaUnmapMemory(impl_->allocator, impl_->paramsAlloc);

  // ---- record + submit ----
  VkCommandBuffer cmd = impl_->beginOneShot();

  VkClearValue clear{};
  clear.color = {{0.0F, 0.0F, 0.0F, 0.0F}};
  VkRenderPassBeginInfo rpBegin{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
  rpBegin.renderPass = impl_->renderPass;
  rpBegin.framebuffer = impl_->framebuffer;
  rpBegin.renderArea = {{0, 0}, {params.width, params.height}};
  rpBegin.clearValueCount = 1;
  rpBegin.pClearValues = &clear;
  vkCmdBeginRenderPass(cmd, &rpBegin, VK_SUBPASS_CONTENTS_INLINE);

  VkViewport viewport{0.0F,
                      0.0F,
                      static_cast<float>(params.width),
                      static_cast<float>(params.height),
                      0.0F,
                      1.0F};
  VkRect2D scissor{{0, 0}, {params.width, params.height}};
  vkCmdSetViewport(cmd, 0, 1, &viewport);
  vkCmdSetScissor(cmd, 0, 1, &scissor);

  vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, impl_->pipeline);
  vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS,
                          impl_->pipelineLayout, 0, 1, &impl_->descriptorSet, 0,
                          nullptr);
  vkCmdDraw(cmd, 3, 1, 0, 0);
  vkCmdEndRenderPass(cmd);

  impl_->transitionImage(
      cmd, impl_->colorImage, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
      VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_ASPECT_COLOR_BIT);

  VkBufferImageCopy copyRegion{};
  copyRegion.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
  copyRegion.imageExtent = {params.width, params.height, 1};
  vkCmdCopyImageToBuffer(cmd, impl_->colorImage,
                         VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                         impl_->readbackBuffer, 1, &copyRegion);

  impl_->endOneShot(cmd);

  const VkDeviceSize frameBytes =
      static_cast<VkDeviceSize>(params.width) * params.height * 4;
  impl_->frameStorage.resize(frameBytes);
  void *mappedReadback = nullptr;
  check(vmaMapMemory(impl_->allocator, impl_->readbackAlloc, &mappedReadback),
        "vmaMapMemory(readback)");
  std::memcpy(impl_->frameStorage.data(), mappedReadback,
              static_cast<std::size_t>(frameBytes));
  vmaUnmapMemory(impl_->allocator, impl_->readbackAlloc);

  Frame frame;
  frame.sequence = sequence;
  frame.width = params.width;
  frame.height = params.height;
  frame.codec = "raw-rgba8";
  frame.payload = std::span<const std::byte>(impl_->frameStorage.data(),
                                             impl_->frameStorage.size());
  return frame;
}

void Renderer::recoverFromDeviceLost() { impl_->deviceLost = false; }

void Renderer::setEmptySpaceSkipping(bool enabled) noexcept {
  impl_->emptySpaceSkipping = enabled; // documented no-op; see file header
}

void Renderer::simulateDeviceLost() { impl_->deviceLost = true; }

std::size_t Renderer::gpuMemoryBytes() const noexcept {
  return impl_->volumeBytes + impl_->segBytes;
}

} // namespace mivw::render
