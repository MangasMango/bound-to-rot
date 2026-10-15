#version 330

in vec2 fragTexCoord;
in vec4 fragColor;

uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform float u_strength;
uniform vec2 u_size;

out vec4 fragColor2;

void main()
{
    vec2 texel_step = vec2(1.0) / u_size * u_strength;

    vec4 color = texture(texture0, fragTexCoord);

    color += texture(texture0, fragTexCoord + texel_step * 1.0);
    color += texture(texture0, fragTexCoord + texel_step * 3.0);
    color += texture(texture0, fragTexCoord + texel_step * 5.0);
    color += texture(texture0, fragTexCoord + texel_step * 7.0);
    color += texture(texture0, fragTexCoord + texel_step * 9.0);
    color += texture(texture0, fragTexCoord + texel_step * 11.0);

    color += texture(texture0, fragTexCoord - texel_step * 1.0);
    color += texture(texture0, fragTexCoord - texel_step * 3.0);
    color += texture(texture0, fragTexCoord - texel_step * 5.0);
    color += texture(texture0, fragTexCoord - texel_step * 7.0);
    color += texture(texture0, fragTexCoord - texel_step * 9.0);
    color += texture(texture0, fragTexCoord - texel_step * 11.0);

    color.rgb = vec3((color.r + color.g + color.b) / 3.0);
    color = color / 9.5;

    fragColor2 = color * colDiffuse * fragColor;
}
