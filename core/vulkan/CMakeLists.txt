# Compiles GLSL to SPIR-V at build time and exposes the results as a target that
# the core library depends on.

set(SHADER_SOURCES
    shaders/raymarch.vert
    shaders/raymarch.frag
    shaders/occupancy_grid.comp
    shaders/mpr.frag
)

set(SPIRV_OUTPUTS)

foreach(SHADER ${SHADER_SOURCES})
    get_filename_component(SHADER_NAME ${SHADER} NAME)
    set(SPIRV "${CMAKE_CURRENT_BINARY_DIR}/spv/${SHADER_NAME}.spv")

    add_custom_command(
        OUTPUT ${SPIRV}
        COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/spv"
        COMMAND Vulkan::glslc
                --target-env=vulkan1.3
                -O
                -Werror
                "${CMAKE_CURRENT_SOURCE_DIR}/${SHADER}"
                -o ${SPIRV}
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${SHADER}"
        COMMENT "Compiling ${SHADER_NAME} to SPIR-V"
        VERBATIM)

    list(APPEND SPIRV_OUTPUTS ${SPIRV})
endforeach()

add_custom_target(mivw_shaders DEPENDS ${SPIRV_OUTPUTS})

# Shaders are embedded in the binary so a deployed build cannot load a modified
# shader from disk.
add_custom_command(
    OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/embedded_shaders.hpp"
    COMMAND ${CMAKE_COMMAND}
            -DSPIRV_DIR=${CMAKE_CURRENT_BINARY_DIR}/spv
            -DOUTPUT=${CMAKE_CURRENT_BINARY_DIR}/embedded_shaders.hpp
            -P "${CMAKE_CURRENT_SOURCE_DIR}/embed_shaders.cmake"
    DEPENDS ${SPIRV_OUTPUTS}
    COMMENT "Embedding SPIR-V modules")

add_custom_target(mivw_embedded_shaders
    DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/embedded_shaders.hpp")
add_dependencies(mivw_shaders mivw_embedded_shaders)
