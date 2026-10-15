#version 330

in vec2 fragTexCoord;
in vec4 fragColor;

uniform sampler2D texture0;
uniform vec4 colDiffuse;

uniform vec2 u_size;
uniform float u_samples;
uniform float u_quality;
uniform float u_threshold;
uniform float u_intensity;

out vec4 finalColor;

void main()
{
    vec4 source = texture(texture0, fragTexCoord);
    vec2 sizeFactor = vec2(1.0) / max(u_size, vec2(1.0)) * max(u_quality, 0.1);

    vec4 sum = vec4(0.0);
    float samplesClamped = max(u_samples, 1.0);
    int range = int((samplesClamped - 1.0) / 2.0);

    for (int x = -range; x <= range; x++)
    {
        for (int y = -range; y <= range; y++)
        {
            vec4 s = texture(texture0, fragTexCoord + vec2(x, y) * sizeFactor);
            float brightness = dot(s.rgb, vec3(0.2126, 0.7152, 0.0722));
            float contribution = smoothstep(u_threshold, u_threshold + 0.15, brightness);
            sum += s * contribution;
        }
    }

    float bloom_strength = max(u_intensity, 0.0) / (samplesClamped * samplesClamped);
    finalColor = source + sum * bloom_strength;
}
