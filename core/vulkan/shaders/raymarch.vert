#version 450
// Full-screen triangle. Computes per-vertex ray origin and direction in the
// volume's texture space so the fragment shader can march without a matrix.

layout(location = 0) out vec3 vRayOriginTex;
layout(location = 1) out vec3 vRayDirTex;

layout(set = 0, binding = 6) uniform CameraBlock {
    mat4 invViewProjection;
    vec4 eyeWorld;        // xyz eye position, w unused
    vec4 volumeMinWorld;  // xyz bounding box min
    vec4 volumeMaxWorld;  // xyz bounding box max
} uCamera;

vec3 worldToTexture(vec3 world) {
    vec3 extent = uCamera.volumeMaxWorld.xyz - uCamera.volumeMinWorld.xyz;
    return (world - uCamera.volumeMinWorld.xyz) / max(extent, vec3(1e-6));
}

void main() {
    // Oversized triangle covering the viewport: cheaper than a quad and avoids
    // the diagonal seam two triangles would introduce.
    vec2 ndc = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2) * 2.0 - 1.0;
    gl_Position = vec4(ndc, 0.0, 1.0);

    vec4 nearPoint = uCamera.invViewProjection * vec4(ndc, 0.0, 1.0);
    vec4 farPoint  = uCamera.invViewProjection * vec4(ndc, 1.0, 1.0);
    nearPoint /= nearPoint.w;
    farPoint  /= farPoint.w;

    vRayOriginTex = worldToTexture(nearPoint.xyz);
    vRayDirTex    = worldToTexture(farPoint.xyz) - vRayOriginTex;
}
