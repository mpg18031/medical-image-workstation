#version 450
// Multi-planar reformat: axial, coronal, sagittal and oblique slices, with
// optional slab thickness rendered as MIP or mean.

layout(location = 0) in  vec2 vUv;
layout(location = 0) out vec4 outColor;

layout(set = 0, binding = 0) uniform sampler3D uVolume;
layout(set = 0, binding = 1) uniform usampler3D uSegmentation;
layout(set = 0, binding = 2) uniform sampler1D uLabelColors;

layout(set = 0, binding = 3) uniform Params {
    vec4  planeOrigin;     // xyz texture-space origin of the slice
    vec4  planeU;          // xyz in-plane axis for the u coordinate
    vec4  planeV;          // xyz in-plane axis for the v coordinate
    vec4  planeNormal;     // xyz slice normal
    vec2  window;          // center, width
    float slabThicknessTex;
    int   slabSamples;
    int   slabMode;        // 0 = single slice, 1 = MIP, 2 = mean
    uint  segmentationVisible;
    float segmentationOpacity;
    float padding0;
} uParams;

float applyWindow(float raw) {
    float lo = uParams.window.x - 0.5 * uParams.window.y;
    return clamp((raw - lo) / max(uParams.window.y, 1e-6), 0.0, 1.0);
}

void main() {
    vec3 base = uParams.planeOrigin.xyz
              + uParams.planeU.xyz * vUv.x
              + uParams.planeV.xyz * vUv.y;

    if (any(lessThan(base, vec3(0.0))) || any(greaterThan(base, vec3(1.0)))) {
        outColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    float value;

    if (uParams.slabMode == 0 || uParams.slabSamples <= 1) {
        value = texture(uVolume, base).r;
    } else {
        // Centre the slab on the requested plane so the crosshair stays at the
        // anatomical position the user selected.
        float step = uParams.slabThicknessTex / float(uParams.slabSamples - 1);
        vec3 start = base - uParams.planeNormal.xyz * (uParams.slabThicknessTex * 0.5);

        value = uParams.slabMode == 1 ? -1e20 : 0.0;

        for (int i = 0; i < uParams.slabSamples; ++i) {
            float sampled = texture(uVolume, start + uParams.planeNormal.xyz * (step * float(i))).r;
            value = uParams.slabMode == 1 ? max(value, sampled) : value + sampled;
        }

        if (uParams.slabMode == 2) {
            value /= float(uParams.slabSamples);
        }
    }

    float intensity = applyWindow(value);
    vec3 color = vec3(intensity);

    if (uParams.segmentationVisible != 0u) {
        uint label = texture(uSegmentation, base).r;
        if (label != 0u) {
            vec4 labelColor = texelFetch(uLabelColors, int(label), 0);
            color = mix(color, labelColor.rgb, uParams.segmentationOpacity);
        }
    }

    outColor = vec4(color, 1.0);
}
