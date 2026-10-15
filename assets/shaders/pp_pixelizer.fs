#version 330

in vec2 fragTexCoord;
in vec4 fragColor;

uniform sampler2D texture0;
uniform vec4 colDiffuse;

uniform vec2 u_size;
uniform float u_pixel_w;
uniform float u_pixel_h;

out vec4 finalColor;

void main()
{
    float dx = u_pixel_w * (1.0 / u_size.x);
    float dy = u_pixel_h * (1.0 / u_size.y);

    vec2 coord = vec2(dx * floor(fragTexCoord.x / dx), dy * floor(fragTexCoord.y / dy));
    vec3 tc = texture(texture0, coord).rgb;

    finalColor = vec4(tc, 1.0);
}
