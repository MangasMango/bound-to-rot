#version 330

// Radial glow — procedural replacement for vfx/glow.png.
// Colour and alpha come entirely from the draw tint, so callers keep
// their own fades (pickup flash, angel halo pulse).
in vec2 fragTexCoord;
in vec4 fragColor;

out vec4 finalColor;

void main() {
    float d = length(fragTexCoord - 0.5) * 2.0;
    float fall = pow(max(0.0, 1.0 - d), 2.0);
    float core = 1.0 - smoothstep(0.0, 0.4, d);
    float a = clamp(fall + core * 0.5, 0.0, 1.0);
    finalColor = vec4(fragColor.rgb, fragColor.a * a);
}
