#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>

namespace mivw::util {

/// Minimal self-contained SHA-256 (FIPS 180-4). Used to fingerprint model
/// artefacts and test fixtures; not exposed for any security-sensitive purpose.
[[nodiscard]] std::array<std::uint8_t, 32>
sha256(std::span<const std::byte> data);
[[nodiscard]] std::array<std::uint8_t, 32>
sha256File(const std::filesystem::path &path);

} // namespace mivw::util
