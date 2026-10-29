#version 330
// Fire-light shader — Godot-style port: log falloff + dual scrolling noise
// churn + noise-perturbed edges + fire color curve. Rendered as a
// multiplicative light map over the scene (0 = dark, 1 = lit).
out vec4 fragColor;

uniform vec2  u_resolution;
uniform float u_ambient;      // 0..1 base light in true darkness
uniform float u_time;
uniform float u_aspect;       // iso squash (step_y / step_x)
uniform int   u_light_count;
uniform vec2  u_light_pos[8]; // screen px (y-up gl_FragCoord space)
uniform vec4  u_light_data[8];// x: radius px, y: flicker, z: strength, w: seed
uniform sampler2D u_noise;    // tiling 256x256 value noise
uniform sampler2D u_curve;    // 64x1 fire gradient LUT
uniform float u_px_scale;     // RT pixels → screen pixels (low-res light maps
                              // keep noise churn at the same screen frequency)
uniform float u_mode;         // 0 = reveal map (multiplied over scene),
                              // 1 = fire glow (added on top, warm colour)

const int MAX_LIGHTS = 8;

// Falloff shaping — real-bulb look: small white-hot core, smooth wide fade.
// FALL_RATE : main gaussian rate. Lower = orange fade reaches farther out
//             (radius scales with 1/sqrt(FALL_RATE); 0.65 ≈ 1.27× the old 1.05).
// CORE_RATE : white-core gaussian rate. Higher = smaller core
//             (radius factor vs the old white zone = sqrt(1.05 / CORE_RATE)).
const float FALL_RATE = 0.65;
const float CORE_RATE = 4.2;
// The passed-in radius is the VISIBLE LIGHT EDGE: with EDGE_SCALE 2.2 the
// gaussian falls to ~ambient at dist == radius. Hub radii are pre-multiplied
// by EDGE_SCALE in _HUB_LIGHTS so their pools keep their tuned size.
const float EDGE_SCALE = 2.2;

float sample_noise(vec2 uv) {
    return texture(u_noise, uv).r;
}

// Godot f1 port — two scrolling noise octaves multiplied = flame churn
float churn(vec2 uv, float t) {
    float a = sample_noise(uv + vec2(t, 0.0));
    float b = sample_noise(uv * 1.3 + vec2(t * 0.8, 0.0));
    return a * b;
}

void main() {
    vec2 pixel = gl_FragCoord.xy;
    vec3 reveal = vec3(0.0);   // multiplied pass: ground-visibility lift
    vec3 glow   = vec3(0.0);   // additive pass: warm fire colour

    for (int i = 0; i < MAX_LIGHTS; i++) {
        if (i >= u_light_count) break;
        vec2 lpos = u_light_pos[i];
        vec4 data = u_light_data[i];
        float radius   = max(data.x, 1.0);
        float flick    = data.y;
        float strength = data.z;
        float seed     = data.w;

        vec2 d = pixel - lpos;
        d.x *= u_aspect;   // iso squash: world circles project WIDE on screen
                           // (y/x = step_y/step_x), so the X axis compresses
        float dist = length(d) / radius * EDGE_SCALE;

        // Flame churn modulates brightness; wide noise wobbles the shape so
        // the pool never reads as a perfect circle.
        vec2 spx = pixel * u_px_scale;      // back to screen-pixel space
        float n = churn(spx / 512.0 + vec2(seed, seed * 0.37),
                        u_time * 0.15 + seed * 7.0);
        float nn = sample_noise(spx / 260.0 + vec2(u_time * 0.06 + seed,
                                                   -u_time * 0.05));
        float dd = max(dist + (nn - 0.5) * 0.25, 0.0);

        // Main gaussian keeps the smooth in→out fade (churn animates it —
        // flame life); the churn floor keeps pools from guttering to black.
        float power = min(strength * 2.2, 1.0);
        float l = min((exp(-dd * dd * FALL_RATE) + exp(-dd * dd * 10.0) * 0.3)
                      * (0.75 + 0.5 * max(n, 0.25)) * power, 1.0)
                  + exp(-dd * dd) * 0.03 * power;

        // White-hot core (flame + saturated floor disc) rides a much tighter
        // gaussian; below the orange band (l ≤ 0.75) the fade is untouched.
        float core = exp(-dd * dd * CORE_RATE);
        float shaped = min(l, 0.75) + 0.25 * core;

        // fire curve: light amount → deep red → orange → yellow → white
        vec3 fire = texture(u_curve, vec2(clamp(shaped, 0.0, 0.97), 0.5)).rgb;

        reveal += vec3(shaped) * 0.50 + fire * l * 0.20;
        glow   += fire * l * 0.115;   // flame layer
    }

    if (u_mode < 0.5) {
        // Dim map — MULTIPLIED over the scene: the unlit world drops to
        // the ambient dim level; light lifts it back toward full brightness.
        fragColor = vec4(clamp(vec3(u_ambient) + reveal * 0.55, 0.0, 1.0), 1.0);
    } else if (u_mode < 1.5) {
        // Warm glow: the fire colour itself, added on top like Stardew's
        // golden saturation around the flame.
        fragColor = vec4(clamp(glow, 0.0, 1.0), 1.0);
    } else if (u_mode < 2.5) {
        // DEBUG: paint dots where the shader believes each light is.
        vec3 col = vec3(0.0);
        for (int i = 0; i < u_light_count; i++) {
            float dpx = length(pixel - u_light_pos[i]);
            if (dpx < 14.0) col = vec3(1.0, 0.0, 0.0);
            if (dpx < 26.0) col = max(col, vec3(1.0, 0.6, 0.0) * (1.0 - (dpx - 14.0) / 12.0));
        }
        fragColor = vec4(col, 1.0);
    } else {
        // DEBUG: light field l as greyscale (positions/radii sanity).
        fragColor = vec4(vec3(min(reveal.r / 0.5, 1.0)), 1.0);
    }
}
