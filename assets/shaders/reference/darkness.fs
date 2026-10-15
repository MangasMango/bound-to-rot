#version 330
out vec4 fragColor;
uniform vec2  u_resolution;
uniform vec2  u_pulse_screen;
uniform vec2  u_player_screen;
uniform float u_pulse_radius_px;
uniform float u_personal_radius_px;
uniform float u_dark_timer;
uniform float u_aspect;

float ell_dist(vec2 a, vec2 b, float aspect) {
    vec2 d = a - b;
    d.y /= aspect;
    return length(d);
}

float falloff(float dist, float radius) {
    float r = max(radius, 1.0);
    return exp(-(dist * dist) / (2.0 * r * r));
}

void main() {
    vec2 pixel = gl_FragCoord.xy;
    float dist_pulse = ell_dist(pixel, u_pulse_screen, u_aspect);
    float dist_player = ell_dist(pixel, u_player_screen, u_aspect);
    float light_pulse = falloff(dist_pulse, u_pulse_radius_px);
    float light_player = falloff(dist_player, u_personal_radius_px);
    vec3 pulse_color = vec3(1.0, 0.82, 0.55);
    vec3 player_color = vec3(0.63, 0.67, 0.78);
    vec3 light = vec3(0.0);
    light += light_pulse * pulse_color;
    light += light_player * player_color;
    float player_dist = distance(u_player_screen, u_pulse_screen);
    if (player_dist > u_pulse_radius_px) {
        float pulse = (sin(u_dark_timer * 4.0) + 1.0) / 2.0;
        light += vec3(0.7 * pulse, 0.0, 0.0);
    }
    light = clamp(light, 0.0, 1.0);
    fragColor = vec4(light, 1.0);
}
