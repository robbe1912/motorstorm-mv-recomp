#pragma once

#include <cstdint>

namespace motorstorm::game {

struct Float4 {
    float value[4];
};

struct Matrix4 {
    Float4 row[4];
};

// Caller-owned host buffers. Parents precede their children; roots parent
// themselves. Local and world matrices occupy separate buffers.
struct WorldTransforms {
    std::uint32_t count;
    const Matrix4* local;
    Matrix4* world;
    const std::uint32_t* parent;
    std::uint32_t* root;
    bool transforms_dirty;
    bool topology_dirty;
};

// Requires x86 AVX/FMA and strict floating-point compilation. Updates host
// buffers only. On invalid inputs or unsupported numeric range, discard the
// pending outputs; callers commit completed results after this returns.
void evaluate_world_transforms(WorldTransforms& transforms);

}
