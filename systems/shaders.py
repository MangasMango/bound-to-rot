# Copyright (C) 2026 MangasMango
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import os
import pyray as rl
from pyray import ffi

_SHADER_DIR = None

def _set_shaders_dir(path):
    global _SHADER_DIR
    _SHADER_DIR = path


class ShaderManager:
    def __init__(self, shaders_dir: str):
        self._dir = shaders_dir
        self._shaders: dict[str, rl.Shader] = {}
        self._uniforms: dict[str, dict[str, int]] = {}
        self._vs_path = os.path.join(shaders_dir, 'default.vs')
        _set_shaders_dir(shaders_dir)
        # Reused uniform buffers - SetShaderValue copies immediately, so a
        # single scratch buffer per type avoids per-call cffi allocations.
        self._fbuf = ffi.new('float *')
        self._ibuf = ffi.new('int *')
        self._v2buf = ffi.new('float[2]')
        self._v4buf = ffi.new('float[4]')
        self._abuf = None        # growable array buffer
        self._abuf_len = 0

    def load(self, name: str, fs_name: str) -> rl.Shader | None:
        fs_path = os.path.join(self._dir, fs_name)
        if not os.path.exists(fs_path):
            return None
        vs = self._vs_path if os.path.exists(self._vs_path) else None
        return self._load_impl(name, fs_path, vs)

    def load_fragment(self, name: str, fs_name: str) -> rl.Shader | None:
        fs_path = os.path.join(self._dir, fs_name)
        if not os.path.exists(fs_path):
            return None
        return self._load_impl(name, fs_path, ffi.NULL)

    def _load_impl(self, name: str, fs_path: str, vs) -> rl.Shader | None:
        try:
            shader = rl.load_shader(vs, fs_path)
        except Exception:
            print(f"[shader] ERROR: Failed to load shader '{name}'")
            import traceback
            traceback.print_exc()
            return None
        if not rl.is_shader_valid(shader):
            return None
        self._shaders[name] = shader
        self._uniforms[name] = {}
        return shader

    def get(self, name: str) -> rl.Shader | None:
        return self._shaders.get(name)

    def has(self, name: str) -> bool:
        return name in self._shaders

    def loc(self, name: str, uniform: str) -> int:
        cache = self._uniforms.get(name)
        if cache is None:
            return -1
        if uniform not in cache:
            shader = self._shaders.get(name)
            if shader is None:
                return -1
            loc = rl.get_shader_location(shader, uniform)
            cache[uniform] = loc
        return cache[uniform]

    def set_float(self, name: str, uniform: str, value: float):
        loc = self.loc(name, uniform)
        if loc < 0:
            print(f"[shader] WARNING: uniform '{uniform}' not found in shader '{name}'")
            return
        self._fbuf[0] = value
        rl.set_shader_value(self._shaders[name], loc, self._fbuf,
                            rl.RL_SHADER_UNIFORM_FLOAT)

    def set_int(self, name: str, uniform: str, value: int):
        loc = self.loc(name, uniform)
        if loc < 0:
            return
        self._ibuf[0] = value
        rl.set_shader_value(self._shaders[name], loc, self._ibuf,
                            rl.RL_SHADER_UNIFORM_INT)

    def set_vec2(self, name: str, uniform: str, x: float, y: float):
        loc = self.loc(name, uniform)
        if loc < 0:
            print(f"[shader] WARNING: uniform '{uniform}' not found in shader '{name}'")
            return
        self._v2buf[0] = x
        self._v2buf[1] = y
        rl.set_shader_value(self._shaders[name], loc, self._v2buf,
                            rl.RL_SHADER_UNIFORM_VEC2)

    def set_vec4(self, name: str, uniform: str, x: float, y: float, z: float, w: float):
        loc = self.loc(name, uniform)
        if loc < 0:
            return
        self._v4buf[0] = x
        self._v4buf[1] = y
        self._v4buf[2] = z
        self._v4buf[3] = w
        rl.set_shader_value(self._shaders[name], loc, self._v4buf,
                            rl.RL_SHADER_UNIFORM_VEC4)

    def set_sampler(self, name: str, uniform: str, texture_id: int):
        """Bind a custom sampler uniform to a real texture unit.

        plain SetShaderValueTexture stores the raw texture id as the sampler
        value, which makes the shader read an unbound texture unit (black);
        SetUniformSampler picks a free unit and binds the texture there.
        """
        loc = self.loc(name, uniform)
        if loc < 0:
            return
        if not hasattr(rl, 'rl_set_uniform_sampler'):
            return
        rl.rl_set_uniform_sampler(loc, texture_id)

    def _array_buf(self, flat: list):
        """Grow-on-demand scratch buffer for uniform arrays."""
        n = len(flat)
        if self._abuf is None or self._abuf_len < n:
            self._abuf = ffi.new('float[]', n)
            self._abuf_len = n
        for i, v in enumerate(flat):
            self._abuf[i] = v
        return self._abuf

    def set_vec2_array(self, name: str, uniform: str, points):
        """Upload a vec2 uniform array (list of (x, y) tuples). Uses the
        array-count variant - plain SetShaderValue only writes ONE element."""
        loc = self.loc(name, uniform)
        if loc < 0:
            return
        flat = []
        for p in points:
            flat.append(float(p[0])); flat.append(float(p[1]))
        rl.set_shader_value_v(self._shaders[name], loc, self._array_buf(flat),
                              rl.RL_SHADER_UNIFORM_VEC2, len(points))

    def set_vec4_array(self, name: str, uniform: str, tuples):
        """Upload a vec4 uniform array (list of (x, y, z, w) tuples)."""
        loc = self.loc(name, uniform)
        if loc < 0:
            return
        flat = []
        for t in tuples:
            flat.extend((float(t[0]), float(t[1]), float(t[2]), float(t[3])))
        rl.set_shader_value_v(self._shaders[name], loc, self._array_buf(flat),
                              rl.RL_SHADER_UNIFORM_VEC4, len(tuples))

    def unload_all(self):
        for name, shader in self._shaders.items():
            try:
                rl.unload_shader(shader)
            except Exception:
                print(f"[shader] WARNING: Failed to unload shader '{name}'")
        self._shaders.clear()
        self._uniforms.clear()
