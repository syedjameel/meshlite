"""Loads GLSL shaders from ``assets/shaders/`` and compiles them.

Falls back to embedded shaders if the asset files can't be located (which
should never happen in a normal install but is useful when running from a
broken working directory or a corrupted install).
"""

from __future__ import annotations

import logging

import moderngl

from meshlite.utils.paths import shaders_dir

_LOGGER = logging.getLogger("meshlite.render.shaders")

_SHADER_DIR = shaders_dir()


_FALLBACK_VERT = """
#version 330
in vec3 in_position;
in vec3 in_normal;
uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
uniform mat3 normal_matrix;
out vec3 v_normal;
out vec3 v_position;
void main() {
    v_normal = normal_matrix * in_normal;
    v_position = vec3(model * vec4(in_position, 1.0));
    gl_Position = projection * view * model * vec4(in_position, 1.0);
}
"""

_FALLBACK_FRAG = """
#version 330
in vec3 v_normal;
in vec3 v_position;
out vec4 f_color;
uniform vec3 light_pos;
uniform vec3 view_pos;
uniform vec3 object_color;
uniform float ambient_strength;
uniform float specular_strength;
uniform float specular_exponent;
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
"""


def _read_shader(name: str) -> str | None:
    path = _SHADER_DIR / name
    try:
        return path.read_text()
    except FileNotFoundError:
        _LOGGER.warning("shader file missing: %s — using fallback", path)
        return None
    except OSError as e:
        _LOGGER.warning("shader read failed: %s (%s) — using fallback", path, e)
        return None


def load_mesh_program(ctx: moderngl.Context) -> moderngl.Program:
    """Compile and link the standard mesh shader program.

    Loads ``mesh.vert`` and ``mesh.frag`` from ``assets/shaders/``. If either
    file is unreadable, embedded fallback shaders are used so the renderer
    can still come up.
    """
    vert = _read_shader("mesh.vert") or _FALLBACK_VERT
    frag = _read_shader("mesh.frag") or _FALLBACK_FRAG
    return ctx.program(vertex_shader=vert, fragment_shader=frag)
