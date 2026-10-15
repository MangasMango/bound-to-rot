#version 330

// Fire burst — procedural replacement for vfx/flame/flame_*.png.
// A noisy, bottom-anchored body narrows as it rises and dies over the
// effect lifetime. u_seed decorrelates simultaneous bursts.
in vec2 fragTexCoord;
in vec4 fragColor;

uniform float u_progress;   // 0..1 over the effect lifetime
uniform float u_seed;       // per-instance hash offset

out vec4 finalColor;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

void main() {
    float t = clamp(u_progress, 0.0, 1.0);
    float hy = 1.0 - fragTexCoord.y;   // 0 at the base, 1 at the tip
    float x  = fragTexCoord.x - 0.5;

    float turb = vnoise(vec2(x * 5.0 + u_seed,
                             hy * 4.0 - t * 6.0)) - 0.5;

    // width shrinks as the flame rises and as the burst dies
    float w = 0.32 * (1.0 - 0.65 * hy) * (1.0 - 0.5 * t);
    float body = 1.0 - smoothstep(w * 0.4, w,
                                  abs(x + turb * 0.22 * (0.3 + hy)));

    // vertical envelope: soft base line, tip retracts upward as t grows
    float tip  = 1.0 - smoothstep(0.35 + 0.5 * t, 0.85, hy + turb * 0.2);
    float base = smoothstep(0.0, 0.08, hy);

    float heat  = clamp(body * tip * base, 0.0, 1.0);
    float core  = heat * heat;                  // white-hot middle

    vec3 col   = mix(fragColor.rgb, vec3(1.0, 0.95, 0.75), core * 0.65);
    float alpha = heat * pow(1.0 - t, 1.3);
    finalColor = vec4(col, fragColor.a * alpha);
}
