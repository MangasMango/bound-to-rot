#version 330
in vec2 fragCoord;
out vec4 fragColor;
uniform float u_flash_intensity;

void main() {
    float alpha = clamp(u_flash_intensity, 0.0, 1.0) * 0.7;
    fragColor = vec4(0.78, 0.0, 0.0, alpha);
}
