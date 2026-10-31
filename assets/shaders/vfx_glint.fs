#version 330

// Sparkle glint - procedural replacement for vfx/glint/glint_*.png.
// Two crossing rays grow outward and retract while a hot core fades.
in vec2 fragTexCoord;
in vec4 fragColor;

uniform float u_progress;   // 0..1 over the effect lifetime

out vec4 finalColor;

void main() {
    float t = clamp(u_progress, 0.0, 1.0);
    vec2 d = fragTexCoord - 0.5;

    // rays grow out on the half-life then retract
    float reach = 0.06 + 0.44 * sin(t * 3.14159265);
    float horiz = exp(-abs(d.y) * 46.0)
                * (1.0 - smoothstep(reach * 0.5, reach, abs(d.x)));
    float vert  = exp(-abs(d.x) * 46.0)
                * (1.0 - smoothstep(reach * 0.5, reach, abs(d.y)));
    float core  = exp(-dot(d, d) * 120.0);

    float alpha = (max(horiz, vert) * 0.9 + core) * pow(1.0 - t, 1.2);
    finalColor = vec4(fragColor.rgb, fragColor.a * clamp(alpha, 0.0, 1.0));
}
