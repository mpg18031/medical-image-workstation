#version 450
// Single-pass volume ray marching with empty-space skipping.
//
// The occupancy grid produced by occupancy_grid.comp lets the loop jump over
// homogeneous regions, which is where most of the speed-up comes from on
// typical CT data (large air and background volumes).

layout(location = 0) in  vec3 vRayOriginTex;
layout(location = 1) in  vec3 vRayDirTex;
layout(location = 0) out vec4 outColor;

layout(set = 0, binding = 0) uniform sampler3D uVolume;
layout(set = 0, binding = 1) uniform sampler1D uTransferFunction;
layout(set = 0, binding = 2) uniform usampler3D uSegmentation;
layout(set = 0, binding = 3) uniform sampler1D uLabelColors;
layout(set = 0, binding = 4) uniform usampler3D uOccupancy;

layout(set = 0, binding = 5) uniform Params {
    vec4  volumeExtentMm;      // xyz extent, w unused
    vec2  window;              // center, width
    float stepSizeTex;
    float segmentationOpacity;
    uint  segmentationVisible;
    uint  occupancyCellsPerAxis;
    float earlyTerminationAlpha;
    float gradientStepTex;
} uParams;

float applyWindow(float raw) {
    float lo = uParams.window.x - 0.5 * uParams.window.y;
    return clamp((raw - lo) / max(uParams.window.y, 1e-6), 0.0, 1.0);
}

vec3 gradientAt(vec3 p) {
    float h = uParams.gradientStepTex;
    return vec3(
        texture(uVolume, p + vec3(h, 0, 0)).r - texture(uVolume, p - vec3(h, 0, 0)).r,
        texture(uVolume, p + vec3(0, h, 0)).r - texture(uVolume, p - vec3(0, h, 0)).r,
        texture(uVolume, p + vec3(0, 0, h)).r - texture(uVolume, p - vec3(0, 0, h)).r);
}

bool cellOccupied(vec3 p) {
    ivec3 cell = ivec3(p * float(uParams.occupancyCellsPerAxis));
    return texelFetch(uOccupancy, cell, 0).r != 0u;
}

// Slab test against the unit cube in texture space.
bool intersectVolume(vec3 origin, vec3 dir, out float tNear, out float tFar) {
    vec3 invDir = 1.0 / dir;
    vec3 t0 = (vec3(0.0) - origin) * invDir;
    vec3 t1 = (vec3(1.0) - origin) * invDir;
    vec3 tmin = min(t0, t1);
    vec3 tmax = max(t0, t1);
    tNear = max(max(tmin.x, tmin.y), tmin.z);
    tFar  = min(min(tmax.x, tmax.y), tmax.z);
    return tFar > max(tNear, 0.0);
}

void main() {
    vec3 dir = normalize(vRayDirTex);
    float tNear, tFar;
    if (!intersectVolume(vRayOriginTex, dir, tNear, tFar)) {
        outColor = vec4(0.0);
        return;
    }

    float t = max(tNear, 0.0);
    float step = uParams.stepSizeTex;
    float emptyStep = 1.0 / float(uParams.occupancyCellsPerAxis);

    vec4 accum = vec4(0.0);

    while (t < tFar && accum.a < uParams.earlyTerminationAlpha) {
        vec3 p = vRayOriginTex + dir * t;

        if (!cellOccupied(p)) {
            t += emptyStep;
            continue;
        }

        float raw = texture(uVolume, p).r;
        vec4 sampleColor = texture(uTransferFunction, applyWindow(raw));

        if (sampleColor.a > 0.0) {
            vec3 grad = gradientAt(p);
            float gradLen = length(grad);
            if (gradLen > 1e-5) {
                vec3 n = grad / gradLen;
                // Headlight shading: light follows the eye, so orientation is
                // never ambiguous while the user rotates.
                float diffuse = abs(dot(n, -dir));
                sampleColor.rgb *= 0.35 + 0.65 * diffuse;
            }

            if (uParams.segmentationVisible != 0u) {
                uint label = texture(uSegmentation, p).r;
                if (label != 0u) {
                    vec4 labelColor = texelFetch(uLabelColors, int(label), 0);
                    sampleColor.rgb = mix(sampleColor.rgb, labelColor.rgb,
                                          uParams.segmentationOpacity);
                }
            }

            // Front-to-back compositing with opacity correction for step size.
            float alpha = 1.0 - pow(1.0 - sampleColor.a, step * 200.0);
            accum.rgb += (1.0 - accum.a) * alpha * sampleColor.rgb;
            accum.a   += (1.0 - accum.a) * alpha;
        }

        t += step;
    }

    outColor = accum;
}
