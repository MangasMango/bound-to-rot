#version 330
uniform vec2 u_center;
uniform float u_radius;
out vec4 finalColor;
void main() {
    vec2 uv = (gl_FragCoord.xy - u_center) / u_radius;
    float sdf = length(uv);
    if (sdf > 1.0) discard;
    finalColor = vec4(1.0, 0.0, 0.0, 1.0);
}
