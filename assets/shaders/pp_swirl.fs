#version 330

in vec2 fragTexCoord;
in vec4 fragColor;

uniform sampler2D texture0;
uniform vec4 colDiffuse;

uniform vec2 u_size;
uniform vec2 u_center;
uniform float u_radius;
uniform float u_angle;

out vec4 finalColor;

void main()
{
    vec2 tc = fragTexCoord * u_size;
    tc -= u_center;

    float dist = length(tc);

    if (dist < u_radius)
    {
        float percent = (u_radius - dist) / u_radius;
        float theta = percent * percent * u_angle * 8.0;
        float s = sin(theta);
        float c = cos(theta);
        tc = vec2(dot(tc, vec2(c, -s)), dot(tc, vec2(s, c)));
    }

    tc += u_center;
    vec4 color = texture(texture0, tc / u_size) * colDiffuse * fragColor;

    finalColor = vec4(color.rgb, 1.0);
}
