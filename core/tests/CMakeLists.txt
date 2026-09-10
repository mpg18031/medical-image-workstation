include(GoogleTest)

add_executable(mivw_tests
    volume/resample_test.cpp
    dicom/deidentifier_test.cpp
    render/golden_image_test.cpp
    infer/spec_validation_test.cpp
)

target_link_libraries(mivw_tests PRIVATE mivw_lib GTest::gtest_main GTest::gmock mivw_warnings)
target_compile_definitions(mivw_tests PRIVATE
    MIVW_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures")

# Labels let CI skip device-dependent suites on runners without a GPU instead of
# failing them.
gtest_discover_tests(mivw_tests
    PROPERTIES LABELS "unit"
    TEST_PREFIX "core."
)

if(MIVW_ENABLE_CUDA)
    add_executable(mivw_gpu_tests
        cuda/window_kernel_test.cu
        cuda/gradient_kernel_test.cu
    )
    target_link_libraries(mivw_gpu_tests PRIVATE mivw_lib GTest::gtest_main)
    gtest_discover_tests(mivw_gpu_tests PROPERTIES LABELS "cuda")
endif()
