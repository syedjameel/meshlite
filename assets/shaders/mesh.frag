#version 330

// Lighting model aligned with MeshInspector/MeshLib's approach:
// simple Phong (ambient + diffuse + specular) with configurable strengths.
// No fill light, no rim light — clean and predictable.

in vec3 v_normal;
in vec3 v_position;

out vec4 f_color;

uniform vec3 light_pos;
uniform vec3 view_pos;
uniform vec3 object_color;

// Configurable lighting params - sent from the renderer each frame.
// Defaults match MeshInspector's typical look.
uniform float ambient_strength;     // default 0.2
uniform float specular_strength;    // default 0.4
uniform float specular_exponent;    // default 35.0

void main() {
    vec3 N = normalize(v_normal);
    vec3 L = normalize(light_pos - v_position);
    vec3 V = normalize(view_pos - v_position);

    // Diffuse (Lambertian)
    float NdotL = max(dot(N, L), 0.0);

    // Specular (Phong reflection)
    vec3 R = reflect(-L, N);
    float spec = pow(max(dot(R, V), 0.0), specular_exponent);

    // Combine
    vec3 ambient  = ambient_strength * vec3(1.0);
    vec3 diffuse  = NdotL * vec3(1.0);
    vec3 specular = specular_strength * spec * vec3(1.0);

    vec3 result = (ambient + diffuse + specular) * object_color;
    result = clamp(result, 0.0, 1.0);

    f_color = vec4(result, 1.0);
}
