#version 330

in vec3 in_position;
in vec3 in_normal;

out vec3 v_normal;
out vec3 v_position;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
uniform mat3 normal_matrix;

void main() {
    v_normal = normal_matrix * in_normal;
    v_position = vec3(model * vec4(in_position, 1.0));
    gl_Position = projection * view * model * vec4(in_position, 1.0);
}
