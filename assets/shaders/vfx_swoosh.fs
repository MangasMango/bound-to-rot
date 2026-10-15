#version 330

// Combat slash arc — procedural replacement for vfx/swoosh/swoosh_*.png.
// A crescent band sweeps open over u_progress, tapers, and fades away.
in vec2 fragTexCoord;
in vec4 fragColor;

uniform float u_progress;   // 0..1 over the effect lifetime

out vec4 finalColor;

void main() {
    float t = clamp(u_progress, 0.0, 1.0);
    vec2 p = fragTexCoord - 0.5;
    float r = length(p);
    float a = atan(p.y, p.x);

    // sweep window opens fast, then the band thins out
    float span  = 2.4 * min(1.0, t * 3.0);      // radians, each side of axis
    float band  = 0.32;                          // band centre radius
    float thick = 0.11 * (1.0 - 0.75 * t);       // tapering half width

    float radial = 1.0 - smoothstep(thick * 0.4, thick, abs(r - band));
    float window = 1.0 - smoothstep(span * 0.75, span, abs(a));

    // brighter leading tip near the sweep edge
    float tip = 1.0 + 0.8 * (1.0 - smoothstep(0.0, 0.6, span - abs(a)));

    float alpha = radial * window * pow(1.0 - t, 1.4) * tip;
    finalColor = vec4(fragColor.rgb, fragColor.a * clamp(alpha, 0.0, 1.0));
}
