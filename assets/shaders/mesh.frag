#version 330

// Phong lighting with a head-light key. The light follows the camera,
// so lit surfaces always face the viewer. The three strength uniforms
// are driven by Preferences (ambient / specular / specular_exponent).

in vec3 v_normal;
in vec3 v_position;

out vec4 f_color;

uniform vec3 light_pos;
uniform vec3 view_pos;
uniform vec3 object_color;

uniform float ambient_strength;     // default 0.35
uniform float specular_strength;    // default 0.6
uniform float specular_exponent;    // default 64.0

void main() {
    vec3 N = normalize(v_normal);
    vec3 L = normalize(light_pos - v_position);
    vec3 V = normalize(view_pos - v_position);
    vec3 R = reflect(-L, N);

    vec3 ambient = ambient_strength * vec3(1.0);

    float NdotL = max(dot(N, L), 0.0);
    vec3 diffuse = NdotL * vec3(1.0);

    float spec = pow(max(dot(V, R), 0.0), specular_exponent);
    vec3 specular = specular_strength * spec * vec3(1.0);

    vec3 result = (ambient + diffuse + specular) * object_color;
    f_color = vec4(clamp(result, 0.0, 1.0), 1.0);
}
