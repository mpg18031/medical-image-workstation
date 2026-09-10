cmake_minimum_required(VERSION 3.28)

project(mivw_core
    VERSION 0.1.0
    DESCRIPTION "Real-Time AI-Powered Medical Image Workstation compute core"
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(MIVW_ENABLE_CUDA     "Build CUDA kernels and TensorRT inference" ON)
option(MIVW_ENABLE_TESTS    "Build the GoogleTest suite" ON)
option(MIVW_ENABLE_SANITIZERS "Build with ASan/UBSan" OFF)

if(MIVW_ENABLE_CUDA)
    enable_language(CUDA)
    set(CMAKE_CUDA_STANDARD 20)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)
    set(CMAKE_CUDA_ARCHITECTURES 75 80 86 89)
endif()

# ---------------------------------------------------------------- dependencies
include(FetchContent)
find_package(Vulkan REQUIRED COMPONENTS glslc)
find_package(Threads REQUIRED)

# Pin by commit SHA, not tag: tags are mutable, SHAs are not.
FetchContent_Declare(pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6)
FetchContent_Declare(googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.15.2)
FetchContent_Declare(vma
    GIT_REPOSITORY https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator.git
    GIT_TAG        v3.1.0)

FetchContent_MakeAvailable(pybind11 vma)
if(MIVW_ENABLE_TESTS)
    FetchContent_MakeAvailable(googletest)
endif()

find_package(DCMTK REQUIRED)     # DICOM parsing
find_package(zstd  REQUIRED)     # volume compression
find_package(PNG   REQUIRED)     # golden-image comparison in tests
find_package(onnxruntime CONFIG REQUIRED)  # inference runtime

# ---------------------------------------------------------------- warnings
add_library(mivw_warnings INTERFACE)
if(MSVC)
    target_compile_options(mivw_warnings INTERFACE $<$<COMPILE_LANGUAGE:CXX>:/W4 /permissive- /WX>)
else()
    target_compile_options(mivw_warnings INTERFACE
        $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wpedantic -Wshadow -Wconversion
        -Wnon-virtual-dtor -Wold-style-cast -Wcast-align -Werror>)
endif()

if(MIVW_ENABLE_SANITIZERS AND NOT MSVC)
    target_compile_options(mivw_warnings INTERFACE
        -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(mivw_warnings INTERFACE -fsanitize=address,undefined)
endif()

# ---------------------------------------------------------------- shaders
add_subdirectory(vulkan)

# ---------------------------------------------------------------- core library
file(GLOB_RECURSE MIVW_SOURCES CONFIGURE_DEPENDS src/*.cpp)
if(MIVW_ENABLE_CUDA)
    file(GLOB_RECURSE MIVW_CUDA_SOURCES CONFIGURE_DEPENDS cuda/*.cu)
else()
    list(APPEND MIVW_SOURCES cpu/cuda_stubs.cpp)
endif()

add_library(mivw_lib STATIC ${MIVW_SOURCES} ${MIVW_CUDA_SOURCES})
target_include_directories(mivw_lib PUBLIC include)
target_include_directories(mivw_lib PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/vulkan)
target_link_libraries(mivw_lib
    PUBLIC  Vulkan::Vulkan GPUOpen::VulkanMemoryAllocator DCMTK::DCMTK
            zstd::libzstd_shared Threads::Threads PNG::PNG onnxruntime::onnxruntime
    PRIVATE mivw_warnings)
# src/testing/phantoms.cpp resolves fixtures relative to the tests fixtures dir.
target_compile_definitions(mivw_lib PRIVATE
    MIVW_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
add_dependencies(mivw_lib mivw_shaders)

if(MIVW_ENABLE_CUDA)
    target_compile_definitions(mivw_lib PUBLIC MIVW_WITH_CUDA=1)
    set_target_properties(mivw_lib PROPERTIES CUDA_SEPARABLE_COMPILATION ON)
endif()

# ---------------------------------------------------------------- python module
pybind11_add_module(mivw_core bindings/module.cpp)
target_link_libraries(mivw_core PRIVATE mivw_lib mivw_warnings)
install(TARGETS mivw_core LIBRARY DESTINATION .)

# ---------------------------------------------------------------- tests
if(MIVW_ENABLE_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
